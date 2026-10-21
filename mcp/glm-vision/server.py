"""视频 diff 定位 MCP server(唯一的工具是 analyze_video_diff)。

像素级 diff 扫描本地视频, 定位画面突变的帧对并产出标注对比图;
语义分析(不连贯的原因是什么)由主模型直接 Read 对比图完成。
本 server 有意不注册"把画面交给视觉模型问答"的工具——那类调用
(多帧 + 视觉模型)耗时远超 MCP 工具超时, 曾是 timeout 的主要来源。

diff 工具内部仅在主体定位(focus=auto)和可选 grounding(mark_glm)时
各发一次廉价 GLM 请求, 不做整段视频的画面问答。

环境变量:
  ZHIPU_API_KEY  可选。缺失时 focus=auto 自动降级为全画面纯像素 diff,
                 mark_glm 被忽略; 配置后仅用于主体定位与可选 grounding
                 (各一次廉价请求), diff 扫描本体始终零 API 费用
  ZHIPU_MODEL    视觉模型名, 默认 glm-4.6v(可换 glm-4.5v / glm-5.3-flash 等, 同一 key 通用)
"""

import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

import imageio_ffmpeg
from mcp.server.fastmcp import FastMCP
from PIL import Image, ImageDraw, ImageFont

try:  # diff 扫描用, 缺失时 analyze_video_diff 优雅报错, 其余工具不受影响
    import cv2
    import numpy as np
    _CV2_OK = True
except ImportError:
    _CV2_OK = False

sys.stdout.reconfigure(encoding="utf-8")

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
API_KEY = os.environ.get("ZHIPU_API_KEY", "")
DEFAULT_MODEL = os.environ.get("ZHIPU_MODEL", "glm-4.6v")

BOX_COLORS = ["#FF3B30", "#FF9500", "#AF52DE", "#34C759", "#007AFF"]

mcp = FastMCP("glm-vision")

SYSTEM_PROMPT = (
    "你是一名严谨的视觉内容分析助手。按顺序观看画面, 只依据用户的问题"
    "如实描述和分析可见内容: 问题要描述就给描述, 要定位问题就给定位, 要判断就给判断。"
    "不要引入画面之外的领域先验, 画面中无法确认的事明确说看不出来。"
)


def _call_glm(model: str, content: list) -> str:
    req = urllib.request.Request(
        API_URL,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        },
    )
    data = None
    # 依次尝试: 关闭思考(4.5V/4.6V 支持) -> 降低思考力度(5.x 始终思考的模型)
    for thinking in ({"type": "disabled"}, {"effort": "low"}, None):
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            # 思考模型可能把大量 token 花在推理上, 预算太小会导致正文为空
            "max_tokens": 16384,
        }
        if thinking:
            body["thinking"] = thinking
        req.data = json.dumps(body).encode("utf-8")
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            if e.code == 400 and b"1210" in e.read() and thinking is not None:
                continue  # 该模型不支持此思考配置, 换下一种
            raise
    msg = data["choices"][0]["message"]
    # 正文为空时兜底取思考内容, 避免静默返回空字符串
    return ((msg.get("content") or "").strip()
            or (msg.get("reasoning_content") or "").strip())


def _probe(video_path: str) -> dict:
    proc = subprocess.run(
        [FFMPEG, "-hide_banner", "-i", video_path],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    err = proc.stderr
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", err)
    if not m:
        raise ValueError(f"无法读取视频信息(可能是损坏文件或不支持的格式):\n{err[-500:]}")
    duration = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    res = re.search(r"(\d{2,5})x(\d{2,5})", err)
    fps = re.search(r"([\d.]+)\s*fps", err)
    return {
        "duration_sec": round(duration, 2),
        "resolution": f"{res.group(1)}x{res.group(2)}" if res else "unknown",
        "fps": float(fps.group(1)) if fps else None,
        "size_mb": round(os.path.getsize(video_path) / 1024 / 1024, 1),
    }


def _extract_frame(video_path: str, t: float, out_path: str, crop=None, scale_w=None) -> None:
    filters = []
    if crop:
        filters.append(f"crop={crop[2]}:{crop[3]}:{crop[0]}:{crop[1]}")
    if scale_w:
        filters.append(f"scale='min({scale_w},iw)':-2")
    vf = ",".join(filters) if filters else "null"
    for attempt in (t, max(0.0, t - 0.25)):
        # 两段式 seek: 输入侧 -ss 关键帧跳到目标前 2s(快), 输出侧 -ss 补差逐帧解码(精确)。
        # 纯输出侧 seek 长视频每个时间点都从头解码, 22s 视频抽 9 帧即超时;
        # 纯输入侧 seek 低 fps 视频会抽到同一关键帧。
        lead = min(2.0, attempt)
        cmd = [FFMPEG, "-y", "-loglevel", "error"]
        if attempt - lead > 0.01:
            cmd += ["-ss", f"{attempt - lead:.4f}"]
        cmd += ["-i", video_path, "-ss", f"{lead:.4f}", "-frames:v", "1",
                "-vf", vf, "-q:v", "2", out_path]
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if proc.returncode == 0 and os.path.isfile(out_path) and os.path.getsize(out_path):
            return
    raise ValueError(f"在 {t:.2f}s 抽帧失败: {proc.stderr[-300:]}")


def _encode_image(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def _get_subject_box(video_path: str, info: dict, model: str, t: float = None):
    """用一帧廉价询问视觉模型拿到主体边界框, 返回像素坐标 (x, y, w, h) 或 None。

    t 缺省取视频中间帧; 主体会移动的素材可传尖峰时刻重新定位。
    """
    w, h = (int(v) for v in info["resolution"].split("x"))
    with tempfile.TemporaryDirectory() as tmp:
        frame = os.path.join(tmp, "box.jpg")
        _extract_frame(video_path, info["duration_sec"] * 0.5 if t is None else t, frame)
        content = [
            {"type": "text", "text":
                "找出画面中的主要人物/角色(动画主体)。只输出其边界框: 4个0到999的整数, "
                "格式: x1,y1,x2,y2 (左上角和右下角, 相对画面宽高的比例坐标乘999)。"
                "画面中没有明确主体人物则只输出: none"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + _encode_image(frame)}},
        ]
    try:
        txt = _call_glm(model, content)
    except Exception:
        return None
    m = re.search(r"(\d{1,3})\D{1,4}(\d{1,3})\D{1,4}(\d{1,3})\D{1,4}(\d{1,3})", txt)
    if not m:
        return None
    x1, y1, x2, y2 = (max(0, min(999, int(v))) for v in m.groups())
    if x2 <= x1 or y2 <= y1:
        return None
    px1, px2 = x1 / 999 * w, x2 / 999 * w
    py1, py2 = y1 / 999 * h, y2 / 999 * h
    mx, my = (px2 - px1) * 0.15, (py2 - py1) * 0.15  # 15% 边距防框偏
    bx1 = max(0, int(px1 - mx))
    by1 = max(0, int(py1 - my))
    bw = min(w, int(px2 + mx)) - bx1
    bh = min(h, int(py2 + my)) - by1
    if bw < 16 or bh < 16:
        return None
    return (bx1, by1, bw, bh)


def _check_common(video_path: str):
    # key 不在这里拦: analyze_video_diff 无 key 时降级为纯像素全画面 diff,
    # key 只在 focus=auto 主体定位与 mark_glm grounding 两处消费
    if not os.path.isfile(video_path):
        return f"错误: 文件不存在: {video_path}"
    return None


def _load_font(size: int):
    for p in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf"):
        if os.path.isfile(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                pass
    return ImageFont.load_default()


JPEG_TARGET_BYTES = 128 * 1024
JPEG_HARD_MAX_BYTES = 256 * 1024


def _save_jpeg_small(img: Image.Image, out_path: str,
                     target_bytes: int = JPEG_TARGET_BYTES,
                     hard_max_bytes: int = JPEG_HARD_MAX_BYTES,
                     start_w: int = 760) -> str:
    """保存视觉证据 JPEG：优先清晰度，目标 <=128 KiB，硬上限 <=256 KiB。

    先在当前尺寸尝试 q95/q90/q85；能达到 target_bytes 就立即返回。
    若 q85 已低于 hard_max_bytes，即使略高于目标也保留当前分辨率；
    只有仍超过硬上限时才继续缩小尺寸。极端高熵画面最后再降低质量兜底。
    """
    w, h = img.size
    p = out_path
    first_w = min(max(1, int(start_w)), w)

    widths = [first_w]
    for tw in (600, 480, 380, 300, 240, 192):
        if tw < first_w and tw not in widths:
            widths.append(tw)

    last_im = img
    for tw in widths:
        im = img if tw >= w else img.resize((tw, round(h * tw / w)), Image.LANCZOS)
        last_im = im
        size = None
        for q in (95, 90, 85):
            im.save(p, "JPEG", quality=q, optimize=True)
            size = os.path.getsize(p)
            if size <= target_bytes:
                return p
        # q85 仍略高于目标但未触及硬上限：保清晰度/分辨率，不再继续缩图。
        if size is not None and size <= hard_max_bytes:
            return p

    # 极端高熵画面兜底：在最小尺寸进一步降质量，确保不越过硬上限。
    for q in (80, 75, 65, 55, 45):
        last_im.save(p, "JPEG", quality=q, optimize=True)
        if os.path.getsize(p) <= hard_max_bytes:
            return p

    return p


def _draw_boxes(img_path: str, boxes: list, labels: list, out_path: str,
                max_width: int = 0) -> str:
    """在图片上画出标注框(坐标为像素值), 可选缩放后保存。"""
    img = Image.open(img_path).convert("RGB")
    w, h = img.size
    draw = ImageDraw.Draw(img)
    lw = max(2, round(min(w, h) / 250))
    font = _load_font(max(14, round(min(w, h) / 30)))
    for i, (x1, y1, x2, y2) in enumerate(boxes):
        color = BOX_COLORS[i % len(BOX_COLORS)]
        draw.rectangle([x1, y1, x2, y2], outline=color, width=lw)
        label = labels[i] if i < len(labels) and labels[i] else f"#{i + 1}"
        tb = draw.textbbox((0, 0), label, font=font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        ty = y1 - th - lw * 5
        if ty < 0:  # 顶部放不下标签时移到框下方
            ty = min(y2 + lw * 2, h - th - lw * 3)
        draw.rectangle([x1, ty - lw, x1 + tw + lw * 5, ty + th + lw], fill=color)
        draw.text((x1 + lw * 2.5, ty - tb[1]), label, font=font, fill="white")
    if max_width and w > max_width:
        img = img.resize((max_width, round(h * max_width / w)), Image.LANCZOS)
    if out_path.lower().endswith(".png"):  # PNG 对游戏画面压不动, 转自适应 JPEG
        out_path = _save_jpeg_small(img, os.path.splitext(out_path)[0] + ".jpg")
    else:
        img.save(out_path)
    return out_path


def _mark_region_impl(image_paths: list[str], question: str, output_path: str,
                      max_width: int) -> str:
    if not API_KEY:
        return "错误: 未设置 ZHIPU_API_KEY 环境变量, 请在 ZCode 的 MCP 配置中填写。"
    if not image_paths:
        return "错误: image_paths 为空"
    for p in image_paths:
        if not os.path.isfile(p):
            return f"错误: 文件不存在: {p}"

    base = image_paths[-1]  # 标注画在最后一张(基准图)上
    try:
        with Image.open(base) as im:
            w, h = im.size
    except Exception as e:
        return f"错误: 无法读取基准图 {base}: {e}"
    if not output_path:
        root, _ = os.path.splitext(base)
        output_path = root + "_marked.png"
    output_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    multi = len(image_paths) > 1
    ask = (f"任务: {question}\n\n"
           "定位规则: 先用简洁中文说明每个标注区域是什么/为什么标它, 然后"
           "每个区域单独一行, 严格按格式输出: BOX: x1,y1,x2,y2 | 短标签\n"
           "坐标是 0~999 的整数(相对图宽高的比例坐标乘999), x1,y1 为左上角, "
           "x2,y2 为右下角; 短标签 2~8 个字。找不到目标就不输出 BOX 行, 说明原因。\n"
           + (f"共 {len(image_paths)} 张图, 按顺序编号; BOX 坐标一律基于"
              f"最后一张(基准图)的画面。" if multi else "BOX 坐标基于这张图的画面。"))
    content = [{"type": "text", "text": ask}]
    for i, p in enumerate(image_paths):
        if multi:
            content.append({"type": "text", "text": f"[图{i}] {os.path.basename(p)}"
                             + ("(基准图)" if i == len(image_paths) - 1 else "")})
        content.append({
            "type": "image_url",
            "image_url": {"url": "data:image/jpeg;base64," + _encode_image(p)},
        })

    text = _call_glm(DEFAULT_MODEL, content) or ""
    found = re.findall(
        r"BOX:\s*(\d{1,5})\D{1,4}(\d{1,5})\D{1,4}(\d{1,5})\D{1,4}(\d{1,5})"
        r"(?:\s*[|｜]\s*([^\n]{1,20}))?", text)
    if not found:
        return ("视觉模型没有给出任何 BOX 坐标, 说明如下, 请调整 question 重试或"
                f"直接参考:\n{text.strip()}")

    boxes, labels = [], []
    for x1, y1, x2, y2, lb in found:
        x1, y1, x2, y2 = (int(v) for v in (x1, y1, x2, y2))
        if max(x1, y1, x2, y2) > 999:  # 模型违约输出了像素坐标, 直接使用
            px = (x1, y1, x2, y2)
        else:
            px = (round(x1 / 999 * w), round(y1 / 999 * h),
                  round(x2 / 999 * w), round(y2 / 999 * h))
        px = (max(0, min(w - 1, px[0])), max(0, min(h - 1, px[1])),
              max(0, min(w - 1, px[2])), max(0, min(h - 1, px[3])))
        if px[2] - px[0] < 4 or px[3] - px[1] < 4:
            continue
        boxes.append(px)
        labels.append((lb or "").strip()[:16])

    if not boxes:
        return ("解析出的 BOX 坐标全部无效(宽高不足 4px), 模型说明如下:\n" + text.strip())

    _draw_boxes(base, boxes, labels, output_path, max_width)
    note = (f"标注图已生成: {output_path}\n基准图: {base} ({w}x{h}, "
            f"共 {len(boxes)} 个标注框, 画在{'最后一张图' if multi else '该图'}上)\n\n"
            f"视觉模型的定位说明:\n{text.strip()}")
    return note


# ===== diff 尖峰定位: 像素级扫描替代视觉模型粗扫, 标注图压到主模型可读 =====

_DIFF_W, _DIFF_H = 320, 180  # 扫描用的缩略尺寸, 内存 O(1), 长视频安全


def _scan_spikes(video_path: str, roi=None) -> dict:
    """流式逐帧 diff(灰度缩略图), 返回 fps/总帧数/基线统计/尖峰段列表。

    roi=(x,y,w,h) 时每帧先裁剪到该区域再算 diff("对主体 diff"): 背景动态不再
    抬高基线/稀释信号, 角色微小形变的信噪比显著提高(loop 接缝检测实测 2 倍+)。
    尖峰分两类: pulse=孤立脉冲(<=3帧且孤立度>=3, 形变候选), action=连续动作段
    (镜头跟随/动作切换, 运动素材的正常现象)。孤立度=峰值/邻域中位, 不看绝对值——
    运动素材镜头跟随会把基线抬高一个量级, 绝对值排序会误导。
    """
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    diffs = []  # (帧i, i->i+1 的 diff)
    prev = None
    i = -1
    while True:
        ok, f = cap.read()
        if not ok:
            break
        i += 1
        if roi:
            rx, ry, rw, rh = roi
            f = f[ry:ry + rh, rx:rx + rw]
        g = cv2.cvtColor(cv2.resize(f, (_DIFF_W, _DIFF_H), interpolation=cv2.INTER_AREA),
                         cv2.COLOR_BGR2GRAY).astype(np.float32)
        if prev is not None:
            diffs.append((i, float(np.abs(g - prev).mean())))
        prev = g
    cap.release()
    if len(diffs) < 8:
        raise ValueError(f"有效帧太少({i + 1}), 无法扫描")
    vals = np.array([d for _, d in diffs])
    med, p99 = float(np.median(vals)), float(np.percentile(vals, 99))
    thr = max(p99 * 0.8, med * 2.5, 0.1)
    dmap = dict(diffs)
    # 高于阈值的帧聚段(间隔<=6帧合并)
    segs: list[list[int]] = []
    for fi, d in diffs:
        if d > thr:
            if segs and fi - segs[-1][1] <= 6:
                segs[-1][1] = fi
            else:
                segs.append([fi, fi])
    half = max(8, int(fps * 0.5))
    spikes = []
    for f0, f1 in segs:
        pk_f, pk_d = max(((f, dmap[f]) for f in range(f0, f1 + 1)), key=lambda x: x[1])
        neigh = [d for f, d in diffs if 3 < abs(f - pk_f) <= half]
        ratio = pk_d / max(float(np.median(neigh)) if neigh else med, 0.05)
        spikes.append({"f0": f0, "f1": f1, "n": f1 - f0 + 1, "pk_f": pk_f,
                       "pk_d": pk_d, "ratio": ratio,
                       "kind": "pulse" if f1 - f0 <= 2 and ratio >= 3 else "action"})
    spikes.sort(key=lambda s: (s["kind"] != "pulse", -s["ratio"]))
    return {"fps": fps, "n": i + 1, "med": med, "p99": p99, "spikes": spikes, "roi": roi}


def _extract_frame_pair(video_path: str, i1: int, i2: int):
    """按帧号抽两帧(内存内 BGR ndarray, 不落盘)。cv2 按帧号 seek 远快于 ffmpeg 从头解码。"""
    cap = cv2.VideoCapture(video_path)
    out = []
    for idx in (i1, i2):
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, f = cap.read()
        if not ok:
            cap.release()
            raise ValueError(f"帧 {idx} 读取失败")
        out.append(f)
    cap.release()
    return out[0], out[1]


def _expand(bx, by, bw, bh, fx, fy, W, H):
    """矩形按宽高比例外扩并夹到画面内。"""
    mx, my = int(bw * fx), int(bh * fy)
    x1, y1 = max(0, bx - mx), max(0, by - my)
    x2, y2 = min(W, bx + bw + mx), min(H, by + bh + my)
    return x1, y1, x2 - x1, y2 - y1


def _inter_ratio(bx, reg):
    """bbox 与 region 的相交面积占 bbox 自身面积的比例。"""
    rx, ry, rw, rh = reg
    ix = max(0, min(rx + rw, bx[0] + bx[2]) - max(rx, bx[0]))
    iy = max(0, min(ry + rh, bx[1] + bx[3]) - max(ry, bx[1]))
    return (ix * iy) / max(1, bx[2] * bx[3])


def _center_in(bx, reg):
    """bbox 中心点是否落在 region 内。

    与 _inter_ratio 配合过滤: 大连通域(底噪跨背景+主体连片)只要尾巴碰到
    主体区就有 0.2+ 的相交比, 中心判定对这类框天然免疫。
    """
    rx, ry, rw, rh = reg
    cx, cy = bx[0] + bx[2] / 2, bx[1] + bx[3] / 2
    return rx <= cx <= rx + rw and ry <= cy <= ry + rh


def _diff_region_image(a, b, boxes, region, title: str, out_path: str) -> str:
    """两帧在给定区域裁剪后并排(角色占比大, 背景/UI 噪声被裁掉), 画差异框。"""
    rx, ry, rw, rh = region
    ca, cb = a[ry:ry + rh, rx:rx + rw], b[ry:ry + rh, rx:rx + rw]
    h, w = ca.shape[:2]
    gap = 8
    canvas = Image.new("RGB", (w * 2 + gap, h + 30), (24, 24, 24))
    canvas.paste(Image.fromarray(cv2.cvtColor(ca, cv2.COLOR_BGR2RGB)), (0, 30))
    canvas.paste(Image.fromarray(cv2.cvtColor(cb, cv2.COLOR_BGR2RGB)), (w + gap, 30))
    dr = ImageDraw.Draw(canvas)
    dr.text((4, 8), f"{title}  裁剪区[{rx},{ry} {rw}x{rh}]  左=前帧 右=后帧(绿框=差异)",
            fill=(255, 255, 120), font=_load_font(15))
    for (bx, by, bw, bh) in boxes:
        for ox in (0, w + gap):
            dr.rectangle([ox + bx - rx, 30 + by - ry, ox + bx - rx + bw, 30 + by - ry + bh],
                         outline=(60, 255, 60), width=4)
    return _save_jpeg_small(canvas, out_path)


def _diff_zoom_image(a, b, box, title: str, out_path: str) -> str:
    x, y, bw, bh = box
    h, w = a.shape[:2]
    m = int(max(bw, bh) * 0.3)
    x1, y1 = max(0, x - m), max(0, y - m)
    x2, y2 = min(w, x + bw + m), min(h, y + bh + m)
    ca, cb = a[y1:y2, x1:x2], b[y1:y2, x1:x2]
    ch, cw = ca.shape[:2]
    # 上采样到每帧 550 宽(拼图 1100): 差异框常只有几十像素, 原分辨率特写在主模型
    # 眼里像素 token 太少; LANCZOS 放大不增信息但让细小形变占满可视分辨率
    zoom_w = 550
    scale = max(1.0, zoom_w / cw)
    if scale > 1.0:
        nh = round(ch * scale)
        ca = cv2.resize(ca, (zoom_w, nh), interpolation=cv2.INTER_LANCZOS4)
        cb = cv2.resize(cb, (zoom_w, nh), interpolation=cv2.INTER_LANCZOS4)
        ch, cw = nh, zoom_w
    gap = 8
    canvas = Image.new("RGB", (cw * 2 + gap, ch + 30), (24, 24, 24))
    canvas.paste(Image.fromarray(cv2.cvtColor(ca, cv2.COLOR_BGR2RGB)), (0, 30))
    canvas.paste(Image.fromarray(cv2.cvtColor(cb, cv2.COLOR_BGR2RGB)), (cw + gap, 30))
    dr = ImageDraw.Draw(canvas)
    dr.text((4, 8), f"{title}  差异特写[{x},{y} {bw}x{bh} x{scale:.1f}]  左=前帧 右=后帧",
            fill=(255, 255, 120), font=_load_font(15))
    for ox in (0, cw + gap):
        dr.rectangle([ox + round((x - x1) * scale), 30 + round((y - y1) * scale),
                      ox + round((x - x1 + bw) * scale), 30 + round((y - y1 + bh) * scale)],
                     outline=(60, 255, 60), width=3)
    return _save_jpeg_small(canvas, out_path, start_w=1100)


def _analyze_video_diff_impl(video_path: str, output_dir: str, max_spikes: int,
                             mark_glm: bool, focus: str) -> str:
    if not _CV2_OK:
        return "错误: 服务器 Python 环境缺少 opencv-python(pip install opencv-python numpy)"
    err = _check_common(video_path)
    if err:
        return err
    # key 纯可选: 缺失时跳过仅有的两处 API 消费点(focus=auto 主体定位、mark_glm
    # grounding), 整条 diff 扫描退化为零 API 费用的纯像素全画面模式
    no_key_note = ""
    if not API_KEY:
        focus = "full"
        mark_glm = False
        no_key_note = ("未配置 ZHIPU_API_KEY: 已跳过主体定位(ROI)与 grounding, "
                       "使用纯像素全画面 diff。\n\n")
    # 主体定位提前到扫描前(focus=auto, 一次廉价 GLM 调用): diff 在主体外扩50%的
    # ROI 内计算("对主体 diff")——背景动态不再抬高基线/稀释信号, 角色微小形变才
    # 可检出; ROI 同时用于差异框过滤(背景火焰/UI 框滤掉)和对比图裁剪。
    info = _probe(video_path)
    W, H = (int(v) for v in info["resolution"].split("x"))
    sub = None
    roi = None
    if focus != "full":
        sub = _get_subject_box(video_path, info, DEFAULT_MODEL)
        if sub:
            roi = _expand(*sub, 0.5, 0.5, W, H)
    try:
        sc = _scan_spikes(video_path, roi)
    except ValueError as e:
        return f"错误: {e}"
    fps, n, med = sc["fps"], sc["n"], sc["med"]
    spikes = sc["spikes"]
    # 主体ROI无尖峰: 可能角色已移出初始定位框。回退全画面二次扫描(零 API)兜底,
    # 防止把"角色不在ROI内"误报成"无异常"
    roi_fallback = False
    if not spikes and roi:
        sc = _scan_spikes(video_path)
        spikes = sc["spikes"]
        roi_fallback = True
    stem = os.path.splitext(os.path.basename(video_path))[0]
    if not spikes:
        scope = f"主体ROI {roi}" if roi else "全画面"
        return (no_key_note
                + f"== diff 扫描: {os.path.basename(video_path)} ({n} 帧 @ {fps:.0f}fps) ==\n"
                f"{scope} diff 平稳(中位 {med:.2f}, p99 {sc['p99']:.2f}), 无高于阈值的尖峰——"
                "未检出孤立突变或异常动作段。")
    if not output_dir:
        output_dir = os.path.splitext(video_path)[0] + "_diff"
    os.makedirs(output_dir, exist_ok=True)

    if focus == "full":
        mode_note = "全画面模式(diff/过滤/出图均为全画面)"
    elif roi_fallback:
        mode_note = (f"主体ROI {roi} 内无尖峰, 已回退全画面扫描"
                     f"(主体定位 {sub} 可能已过期, 差异不再按主体过滤)")
        sub = None
    elif sub:
        mode_note = (f"主体聚焦模式(主体框 {sub}, ROI {roi}; diff 仅在 ROI 内计算, "
                     "差异框只保留与主体相交的)")
    else:
        mode_note = "全画面模式(主体定位失败, 自动退回)"

    shown = spikes[:max(1, max_spikes)]
    lines = [f"== diff 尖峰分析: {os.path.basename(video_path)} "
             f"({n} 帧 @ {fps:.0f}fps = {n / fps:.2f}s) ==",
             f"基线({'ROI内' if roi and not roi_fallback else '全画面'}): "
             f"中位 {med:.2f} / p99 {sc['p99']:.2f}"
             " (判断看孤立度不看绝对值)",
             mode_note,
             f"尖峰 {len(shown)}/{len(spikes)} 个; pulse=孤立脉冲·形变候选, action=连续动作段:"]
    made = []
    for k, s in enumerate(shown, 1):
        # dmap 的 key i 表示 i-1->i 的 diff, 过阈段 [f0..f1] 每帧都在变。
        # "跳变瞬间"取段内 diff 最大的帧对 (pk_f-1 -> pk_f): 段首尾对比会把
        # 衰减后的稳定态当"后帧"——实测循环接缝帧73->76 的首尾图看不出瞬间
        # 跳变(脚已落定), 峰值帧对 73->74 才是形变瞬间(脚部区 diff 峰值 4.76
        # 对基线 0.02)
        i1, i2 = max(0, s["pk_f"] - 1), min(s["pk_f"], n - 1)
        if i1 >= i2:
            i1 = max(0, i2 - 1)
        try:
            a, b = _extract_frame_pair(video_path, i1, i2)
        except ValueError as e:
            lines.append(f"尖峰{k} 帧{i1}->{i2}: 抽帧失败({e})")
            continue
        # 全分辨率帧对 diff -> 差异 bbox(纯代码定位, 不依赖模型眼力)。
        # 阈值固定 25: 动态阈值(mean+3σ)会被镜头移动的背景噪声抬高, 反把角色
        # 真实变化滤掉; 背景噪声框交给主体相交过滤处理
        # diff 前高斯预滤波: 抹掉 TAA 亚像素抖动和录屏压缩伪影造成的高频底噪
        # (离线实测残差降 20-40%), 角色形变的轮廓错位(>=2px)保留
        fa = cv2.GaussianBlur(a, (3, 3), 0)
        fb = cv2.GaussianBlur(b, (3, 3), 0)
        d = cv2.absdiff(fb, fa).max(axis=2)
        mask = (d > 25).astype(np.uint8)
        mask = cv2.dilate(mask, np.ones((7, 7), np.uint8), iterations=2)
        ncomp, _, stats, _ = cv2.connectedComponentsWithStats(mask)
        area_min = 0.0005 * a.shape[0] * a.shape[1]
        boxes = sorted((tuple(int(v) for v in st[:4]) for st in stats[1:] if st[4] >= area_min),
                       key=lambda bx: -(bx[2] * bx[3]))[:4]
        # 定位只对 pulse(1~3帧, 镜头近静止)可靠: action 跨多帧伴随镜头跟随移动,
        # 帧对 diff 的 bbox 必然全屏化(实测占比0.67+), 画任何框都是误导。
        # 全屏框(>0.5画面)本身也无定位意义, 对应淡入淡出/闪白/剪辑切换
        big = [bx for bx in boxes if bx[2] * bx[3] <= 0.5 * W * H]
        # 最大框即全屏级 => 主变化是整幅画面的(淡入/闪白/剪辑), 残余小框无意义
        full_screen = bool(boxes) and boxes[0][2] * boxes[0][3] > 0.5 * W * H
        reg, note, dropped = (0, 0, W, H), "", []
        if s["kind"] == "action":
            kept = []
            note = "(动作段只出前后帧供粗看, 跨帧镜头移动使局部定位不可靠)"
        elif full_screen:
            kept = []
            note = "(全屏级变化: 淡入淡出/闪白/剪辑切换类, 无局部定位意义)"
        elif sub:
            # 主体聚焦: 过滤与裁剪职责分离——差异框过滤用主体框外扩20%的紧框
            # (挡住 ROI 内的背景动态, 如角色头顶的蒸汽), 出图裁剪仍用外扩50%的
            # 宽框(保留环境上下文)。中心判定拦住"尾巴碰到主体区"的底噪大连片。
            # 紧框内无差异框时先按尖峰帧重定位主体(角色会移动); 重定位后仍无
            # 角色相关差异, 判定背景动态不画框
            reg = _expand(*sub, 0.5, 0.5, W, H)
            freg = _expand(*sub, 0.2, 0.2, W, H)
            kept = [bx for bx in big if _inter_ratio(bx, freg) >= 0.2 and _center_in(bx, freg)]
            if not kept:
                sub2 = _get_subject_box(video_path, info, DEFAULT_MODEL, i2 / fps)
                if sub2:
                    freg = _expand(*sub2, 0.2, 0.2, W, H)
                    reg = _expand(*sub2, 0.5, 0.5, W, H)
                    kept = [bx for bx in big if _inter_ratio(bx, freg) >= 0.2 and _center_in(bx, freg)]
                    if kept:
                        note = "(主体已移动, 按尖峰帧重定位)"
            if kept:
                dropped = [bx for bx in big
                           if not (_inter_ratio(bx, freg) >= 0.2 and _center_in(bx, freg))]
                if dropped and not note:
                    note = f"(过滤主体外差异{len(dropped)}处)"
            else:
                # kept 为空分两种情形, 报告要区分: 底噪把角色差异连进大连通域时
                # (TAA/压缩伪影 + 真实变化连通), 不是"没有主体差异"而是"无法定位"
                blob = [bx for bx in boxes if bx[2] * bx[3] > 0.15 * W * H
                        and _inter_ratio(bx, freg) >= 0.2]
                note = ("(差异与背景底噪连片, 无法局部定位, 请直接对比前后帧)" if blob
                        else "(脉冲差异未落在主体上, 判定为背景动态)")
        else:
            kept = big
        tag = "孤立脉冲·形变候选" if s["kind"] == "pulse" else "连续动作段"
        fp = os.path.abspath(os.path.join(output_dir,
                              f"{stem}_spike{k}_{i1 / fps:.3f}s_full.jpg"))
        _diff_region_image(a, b, kept, reg, f"t={i1 / fps:.3f}s (帧{i1})", fp)
        made.append(fp)
        entry = (f"尖峰{k} [{tag}] 帧{i1}->{i2} (t={i1 / fps:.3f}s) 峰值diff={s['pk_d']:.2f} "
                 f"孤立度{s['ratio']:.1f}x 持续{s['n']}帧 "
                 f"角色相关差异区{len(kept)}处{note}\n"
                 f"  对比图: {fp}")
        if dropped:
            entry += f"\n  主体外差异(背景/特效/UI, 未入图): {dropped}"
        if s["kind"] == "pulse" and kept:
            zp = os.path.abspath(os.path.join(output_dir,
                                  f"{stem}_spike{k}_{i1 / fps:.3f}s_zoom.jpg"))
            _diff_zoom_image(a, b, kept[0], f"t={i2 / fps:.3f}s", zp)
            made.append(zp)
            entry += f"\n  差异放大: {zp} (最大差异区 {kept[0]})"
        lines.append(entry)
    # 可选: GLM grounding 对 top1 脉冲做语义标注(付费一次, 默认关; 纯 bbox 已够定位)
    if mark_glm and shown[0]["kind"] == "pulse":
        i1, i2 = max(0, shown[0]["pk_f"] - 1), min(shown[0]["pk_f"], n - 1)
        a, b = _extract_frame_pair(video_path, i1, i2)
        tmpd = tempfile.mkdtemp(prefix="diffglm_")
        pa = os.path.join(tmpd, "a.png")
        pb = os.path.join(tmpd, "b.png")
        Image.fromarray(cv2.cvtColor(a, cv2.COLOR_BGR2RGB)).save(pa)
        Image.fromarray(cv2.cvtColor(b, cv2.COLOR_BGR2RGB)).save(pb)
        mp = os.path.abspath(os.path.join(output_dir, f"{stem}_spike1_glm_marked.jpg"))
        gtxt = _mark_region_impl([pa, pb],
                                 "对比前后两帧, 只把第二帧中角色身上与第一帧不同的变化区域"
                                 "标注出来, 忽略背景、特效和 UI 文字。",
                                 mp, 800)
        lines.append(f"GLM grounding 标注(top1 尖峰, 语义参考):\n{gtxt}")
        made.append(mp)
    lines.append("阅读顺序: 先看各尖峰对比图(左=前帧 右=后帧, 绿框=像素差异区域), "
                 "形变候选再看放大图; 定位与分类由本工具负责, 结论由主模型看图给出。")
    return no_key_note + "\n\n".join(lines)


@mcp.tool()
def analyze_video_diff(video_path: str, output_dir: str = "", max_spikes: int = 6,
                       mark_glm: bool = False, focus: str = "auto") -> str:
    """像素级 diff 扫描视频, 定位画面突变的帧对并产出标注对比图(基本零 API 费用)。

    适合"找出画面异常发生在哪几帧"类任务: 动画循环接缝跳变、瞬间形变/穿模、
    闪白闪烁等, 以及对整段验收素材做"有没有异常突变"的阴性筛查。
    流程: 全片流式逐帧 diff(内存 O(1), 长视频安全) -> 尖峰聚类分类(孤立脉冲=
    形变候选 / 连续动作段=镜头或动作的正常剧烈变化) -> 对每个尖峰按帧号抽前后
    两帧, 用像素差异 bbox 在并排对比图上圈出变化区域 -> 输出压到主模型可读的
    JPEG(视觉证据豁免档内), 主模型直接 Read 看图下结论。
    focus=auto 时先定位角色主体并外扩50%框定 ROI, diff 在 ROI 内计算("对主体
    diff"): 背景动态不参与基线, 角色微小形变可检出; 差异框只保留与主体相交的,
    对比图裁剪到 ROI(角色占比大, 看细节清楚)。主体ROI无尖峰时自动回退全画面
    二次扫描兜底, 角色移动出框时按尖峰帧重定位。定位归本工具, 语义判断归主模型。
    判据是"孤立度"(峰值/邻域中位)而非绝对值: 运动素材镜头跟随会抬高全片基线,
    孤立脉冲和动作段因此可分。

    Args:
        video_path: 视频文件绝对路径。
        output_dir: 对比图输出目录, 默认为视频同目录下 <视频名>_diff/。
        max_spikes: 最多产出的尖峰数(按 孤立脉冲优先→孤立度降序 排序), 默认 6。
        mark_glm: true 时对 top1 孤立脉冲额外调一次 GLM grounding 圈语义差异
            (花一次 API 费用; 默认 false, 纯像素 bbox 已够定位; 未配置
            ZHIPU_API_KEY 时被忽略)。
        focus: "auto"=先定位角色主体并外扩50%框定ROI, diff 在 ROI 内计算, 只圈
            角色相关差异并裁剪出图(多花一次廉价 GLM 调用; 未配置 ZHIPU_API_KEY
            时自动降级为 "full"); "full"=全画面不过滤(零费用, 背景动态也会被圈出)。
    """
    return _analyze_video_diff_impl(video_path, output_dir, max_spikes, mark_glm, focus)


if __name__ == "__main__":
    mcp.run(transport="stdio")

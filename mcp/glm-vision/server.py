"""视频 diff 定位 MCP server(零模型依赖, 纯本地像素计算)。

像素级 diff 扫描本地视频, 定位画面突变的帧对并产出标注对比图;
语义分析(不连贯的原因是什么)由主模型直接 Read 对比图完成。

主体定位同样归主模型: probe_frame 抽一帧回传路径, 主模型看图标注主体框,
再作为 subject 参数回传, 本 server 沿用固定外扩链(15% 容错边距 -> 50% 宽框
ROI -> 20% 紧框过滤)在 ROI 内 diff。本 server 不发起任何网络请求, 无凭据。

两个工具:
  probe_frame          抽单帧供主模型标注主体(工作流第一步)
  analyze_video_diff   diff 扫描主体 ROI 或全画面, 定位突变帧对(第二步)
"""

import os
import re
import subprocess
import sys

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

mcp = FastMCP("glm-vision")


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


def _check_common(video_path: str):
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


def _resolution(info: dict) -> tuple:
    r = info.get("resolution", "unknown")
    try:
        w, h = (int(v) for v in r.split("x"))
        return w, h
    except ValueError:
        raise ValueError(f"无法解析视频分辨率({r}), 该文件可能不受支持")


def _parse_subject(subject: str, W: int, H: int):
    """解析主模型标注的主体框 "x,y,w,h"(像素), 加 15% 边距防框偏。

    返回 (box, err): box=(x, y, w, h) 像素元组, err 非 None 时 box 为 None。
    """
    nums = re.findall(r"-?\d+", subject)
    if len(nums) != 4:
        return None, (f"subject 需要 4 个整数 'x,y,w,h'(像素), 实得 {len(nums)} 个: "
                      f"{subject.strip()!r}")
    x, y, w, h = (int(v) for v in nums)
    x, y = max(0, x), max(0, y)
    w, h = min(w, W - x), min(h, H - y)
    if w < 16 or h < 16:
        return None, (f"subject 框过小或越界: 解析为 ({x},{y},{w},{h}) @ {W}x{H}, "
                      "需要宽高 >= 16px 且在画面内")
    mx, my = w * 0.15, h * 0.15  # 15% 边距防框偏(与旧 GLM 定位链一致)
    bx1, by1 = max(0, int(x - mx)), max(0, int(y - my))
    bw = min(W, int(x + w + mx)) - bx1
    bh = min(H, int(y + h + my)) - by1
    return (bx1, by1, bw, bh), None


def _analyze_video_diff_impl(video_path: str, output_dir: str, max_spikes: int,
                             subject: str) -> str:
    if not _CV2_OK:
        return "错误: 服务器 Python 环境缺少 opencv-python(pip install opencv-python numpy)"
    err = _check_common(video_path)
    if err:
        return err
    try:
        info = _probe(video_path)
        W, H = _resolution(info)
    except ValueError as e:
        return f"错误: {e}"
    sub = None
    if subject.strip():
        sub, sub_err = _parse_subject(subject, W, H)
        if sub_err:
            return f"错误: {sub_err}"
    # 主体聚焦(subject 由主模型经 probe_frame 标注回传): diff 在主体外扩50%的
    # ROI 内计算("对主体 diff")——背景动态不再抬高基线/稀释信号, 角色微小形变
    # 才可检出; ROI 同时用于差异框过滤(外扩20%紧框)和对比图裁剪。
    roi = _expand(*sub, 0.5, 0.5, W, H) if sub else None
    try:
        sc = _scan_spikes(video_path, roi)
    except ValueError as e:
        return f"错误: {e}"
    fps, n, med = sc["fps"], sc["n"], sc["med"]
    spikes = sc["spikes"]
    # 主体ROI无尖峰: 可能角色已移出标注框。回退全画面二次扫描(纯像素)兜底,
    # 防止把"角色不在ROI内"误报成"无异常"
    roi_fallback = False
    if not spikes and roi:
        sc = _scan_spikes(video_path)
        spikes = sc["spikes"]
        roi_fallback = True
    stem = os.path.splitext(os.path.basename(video_path))[0]
    if not spikes:
        scope = f"主体ROI {roi}" if roi and not roi_fallback else "全画面"
        return (f"== diff 扫描: {os.path.basename(video_path)} ({n} 帧 @ {fps:.0f}fps) ==\n"
                f"{scope} diff 平稳(中位 {med:.2f}, p99 {sc['p99']:.2f}), 无高于阈值的尖峰——"
                "未检出孤立突变或异常动作段。")
    if not output_dir:
        output_dir = os.path.splitext(video_path)[0] + "_diff"
    os.makedirs(output_dir, exist_ok=True)

    if roi_fallback:
        mode_note = (f"标注主体ROI {roi} 内无尖峰, 已回退全画面扫描"
                     "(主体可能已移动出框, 差异不再按主体过滤)")
        sub = None
    elif sub:
        mode_note = (f"主体聚焦模式(主体框 {sub}, ROI {roi}; diff 仅在 ROI 内计算, "
                     "差异框只保留与主体相交的)")
    else:
        mode_note = "全画面模式(未提供 subject, 背景动态也会被圈出)"

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
            reg = _expand(*sub, 0.5, 0.5, W, H)
            freg = _expand(*sub, 0.2, 0.2, W, H)
            kept = [bx for bx in big if _inter_ratio(bx, freg) >= 0.2 and _center_in(bx, freg)]
            if kept:
                dropped = [bx for bx in big
                           if not (_inter_ratio(bx, freg) >= 0.2 and _center_in(bx, freg))]
                if dropped:
                    note = f"(过滤主体外差异{len(dropped)}处)"
            else:
                # kept 为空分两种情形, 报告要区分: 底噪把角色差异连进大连通域时
                # (TAA/压缩伪影 + 真实变化连通), 不是"没有主体差异"而是"无法定位";
                # 否则要么真是背景动态, 要么主体已移动出主模型标注的框
                blob = [bx for bx in boxes if bx[2] * bx[3] > 0.15 * W * H
                        and _inter_ratio(bx, freg) >= 0.2]
                note = ("(差异与背景底噪连片, 无法局部定位, 请直接对比前后帧)" if blob
                        else "(脉冲差异未落在标注主体上: 背景动态, 或主体已移动出框——"
                             f"可 probe_frame(t={i2 / fps:.3f}) 重新标注后重扫)")
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
    lines.append("阅读顺序: 先看各尖峰对比图(左=前帧 右=后帧, 绿框=像素差异区域), "
                 "形变候选再看放大图; 定位与分类由本工具负责, 结论由主模型看图给出。")
    return "\n\n".join(lines)


@mcp.tool()
def analyze_video_diff(video_path: str, output_dir: str = "", max_spikes: int = 6,
                       subject: str = "") -> str:
    """视频 diff 工具: 像素级扫描画面突变帧对并产出标注对比图。不做视频内容理解。

    适合"找出画面异常发生在哪几帧"类任务: 动画循环接缝跳变、瞬间形变/穿模、
    闪白闪烁等, 以及整段验收素材的"有没有异常突变"阴性筛查。本工具不理解、
    不描述视频内容, 不要用于看剧情、视频问答、连续看画面等任务; 语义结论由
    主模型 Read 对比图给出。

    推荐工作流(画面有明确主体时):
    1) probe_frame 抽一帧 -> 主模型 Read 帧图, 定位主要角色/主体;
    2) 主体框以 subject="x,y,w,h"(像素) 传入本工具 -> diff 在主体外扩50%的
       ROI 内计算: 背景动态不参与基线, 角色微小形变可检出; 差异框只保留与
       主体相交的, 对比图裁剪到 ROI。ROI 内无尖峰时自动回退全画面二次扫描。
    无 subject 时为全画面模式(背景动态也会被圈出), 适合快速筛查。
    判据是"孤立度"(峰值/邻域中位)而非绝对值: 运动素材镜头跟随会抬高全片
    基线, 孤立脉冲和动作段因此可分。

    Args:
        video_path: 视频文件绝对路径。
        output_dir: 对比图输出目录, 默认为视频同目录下 <视频名>_diff/。
        max_spikes: 最多产出的尖峰数(按 孤立脉冲优先→孤立度降序 排序), 默认 6。
        subject: 主体框像素坐标 "x,y,w,h"(probe_frame 工作流第二步, 见上);
            省略时全画面扫描。
    """
    return _analyze_video_diff_impl(video_path, output_dir, max_spikes, subject)


@mcp.tool()
def probe_frame(video_path: str, t: str = "") -> str:
    """抽取视频的单帧供主模型查看并标注主体(analyze_video_diff 工作流第一步)。

    只抽一帧, 仅服务于"标注主体→ROI diff"流程。本工具不理解视频内容,
    不要用于浏览视频、看剧情、连续抽帧等任务。
    返回帧图路径 + 视频元信息 + 标注协议; 主模型 Read 帧图后按协议以像素
    坐标返回主体框, 再作为 subject 参数调用 analyze_video_diff。

    Args:
        video_path: 视频文件绝对路径。
        t: 抽帧时刻(秒), 如 "12.5"; 省略时取视频中间帧。主体会移动的素材可在
            analyze_video_diff 报告提示的尖峰时刻重新抽帧标注。
    """
    if not os.path.isfile(video_path):
        return f"错误: 文件不存在: {video_path}"
    try:
        info = _probe(video_path)
        W, H = _resolution(info)
    except ValueError as e:
        return f"错误: {e}"
    try:
        t_sec = info["duration_sec"] * 0.5 if not t.strip() else float(t)
    except ValueError:
        return f"错误: t 需要 seconds 数值, 实得 {t.strip()!r}"
    t_sec = max(0.0, min(t_sec, max(0.0, info["duration_sec"] - 0.05)))
    stem = os.path.splitext(os.path.basename(video_path))[0]
    out_dir = os.path.splitext(video_path)[0] + "_diff"
    os.makedirs(out_dir, exist_ok=True)
    fp = os.path.abspath(os.path.join(out_dir, f"{stem}_probe_{t_sec:.3f}s.jpg"))
    try:
        _extract_frame(video_path, t_sec, fp)
    except ValueError as e:
        return f"错误: {e}"
    # 复用视觉证据压缩: 主模型读图的 token 开销有界(<=256KiB)
    with Image.open(fp) as im:
        _save_jpeg_small(im.convert("RGB"), fp)
    return (f"== probe_frame: {os.path.basename(video_path)} @ {t_sec:.3f}s ==\n"
            f"帧图: {fp}\n"
            f"视频: {W}x{H}, 时长 {info['duration_sec']}s, "
            f"{(info['fps'] or 0):.0f}fps, {info['size_mb']}MB\n\n"
            f"标注协议: Read 上面的帧图, 定位画面中的主要人物/角色(动画主体), "
            f"以像素坐标返回主体框 \"x,y,w,h\"(x,y=左上角, w,h=宽高, 基于 {W}x{H} 画面)。"
            f"随后调用 analyze_video_diff(video_path={video_path!r}, subject=\"x,y,w,h\") "
            f"在主体 ROI 内 diff。无明确主体或做全画面筛查时 subject 省略。")


if __name__ == "__main__":
    mcp.run(transport="stdio")

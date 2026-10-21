#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""离线预测：给定头骨旋转，各区域皮肤被拖动多少（线性混合蒙皮，只读）。

动机（J018）：实机"脖子有点歪、颈根变形"。此前的判据都是**静态**权重统计，
而症状是**动态**的（头动时出现）。本工具直接算：把头骨绕自身原点转 N 度，
颈柱/领口/脸的皮肤各被拖动多少厘米。

关键的、此前没人量过的量：**头骨枢轴的位置**。
  `Head_00` 相对 `Neck_00` 的局部平移——
  三个正常包（npc002/npc017/npc746/Golden J017）都是 (0, 0.0486~0.0608, 0.0035~0.0044)
  （枢轴在颈顶/环椎），npc709 是 (0, 0.128, 0.035)（枢轴在半头高）。
  枢轴越高 ⇒ 同一角度下，离枢轴远的颈顶皮肤被甩得越远 ⇒ "歪"。
  76 份玩家外观 mesh 的该值主峰也是 0.075~0.090（0.128 仅 2 份）。

用法：
  skin_motion_predict.py MESH... --deg 15 --axis roll
  skin_motion_predict.py MESH --head-local-y 0.0608 --head-local-z 0.0044   # 模拟下移枢轴

`--head-local-y/z` 是**同时改绑定骨架与运行时骨架**（运行时 = mesh 自身骨架），
所以绑定姿态下形变恒为 0（脚本会自检），只改"绕哪个点转"。

只读：不写任何资源。
"""

from __future__ import annotations

import argparse
import json
import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mesh_skeleton import (  # noqa: E402
    SUPPORTED_MESH_VERSION,
    ManualReviewRequired,
    load_mesh_skeleton,
)
from mesh_rebind_bones import (  # noqa: E402
    BONE_ELEM_SIZE,
    N_INFLUENCE,
    locate_geometry,
    read_positions,
    read_skin_slots,
)
import head_neck_axis as hna  # noqa: E402

HEAD, NECK = "Head_00", "Neck_00"


def local_matrix(j):
    return hna._local_matrix(j)


def inv_affine(m):
    """行向量约定 p' = p·A + t 的逆（4x4 行主序）。"""
    a = (m[0], m[1], m[2], m[4], m[5], m[6], m[8], m[9], m[10])
    det = (a[0] * (a[4] * a[8] - a[5] * a[7])
           - a[1] * (a[3] * a[8] - a[5] * a[6])
           + a[2] * (a[3] * a[7] - a[4] * a[6]))
    if abs(det) < 1e-12:
        raise ManualReviewRequired("局部矩阵不可逆")
    inv = [
        (a[4] * a[8] - a[5] * a[7]) / det, (a[2] * a[7] - a[1] * a[8]) / det, (a[1] * a[5] - a[2] * a[4]) / det,
        (a[5] * a[6] - a[3] * a[8]) / det, (a[0] * a[8] - a[2] * a[6]) / det, (a[2] * a[3] - a[0] * a[5]) / det,
        (a[3] * a[7] - a[4] * a[6]) / det, (a[1] * a[6] - a[0] * a[7]) / det, (a[0] * a[4] - a[1] * a[3]) / det,
    ]
    t = (m[12], m[13], m[14])
    # 逆平移 = -t · A^{-1}
    it = (
        -(t[0] * inv[0] + t[1] * inv[3] + t[2] * inv[6]),
        -(t[0] * inv[1] + t[1] * inv[4] + t[2] * inv[7]),
        -(t[0] * inv[2] + t[1] * inv[5] + t[2] * inv[8]),
    )
    return [inv[0], inv[1], inv[2], 0.0,
            inv[3], inv[4], inv[5], 0.0,
            inv[6], inv[7], inv[8], 0.0,
            it[0], it[1], it[2], 1.0]


def rot4(axis, deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    if axis == "pitch":       # 绕 x（点头）
        r = [1, 0, 0, 0, c, s, 0, -s, c]
    elif axis == "yaw":       # 绕 y（转头）
        r = [c, 0, -s, 0, 1, 0, s, 0, c]
    else:                     # roll：绕 z（侧倾 = “歪”）
        r = [c, s, 0, -s, c, 0, 0, 0, 1]
    return [r[0], r[1], r[2], 0.0, r[3], r[4], r[5], 0.0, r[6], r[7], r[8], 0.0, 0.0, 0.0, 0.0, 1.0]


def fk(locals_by_index, joints, count):
    memo = {}

    def walk(i, depth):
        if i in memo:
            return memo[i]
        if depth > 512:
            raise ManualReviewRequired("骨层级过深，疑似环")
        p = joints[i].parent_index
        w = hna._mat_mul(locals_by_index[i], walk(p, depth + 1)) \
            if 0 <= p < count and p != i else locals_by_index[i]
        memo[i] = w
        return w

    for i in range(count):
        walk(i, 0)
    return memo


def pct(xs, q):
    if not xs:
        return 0.0
    s = sorted(xs)
    return s[min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))]


def analyse(path, deg, axis, head_y=None, head_z=None, label=None, dom_in=None,
            crease=False, binw=0.004, rotate=(), centerline=False):
    allowed = (SUPPORTED_MESH_VERSION,)
    data = Path(path).read_bytes()
    geo = locate_geometry(data, allowed)
    sk = load_mesh_skeleton(path, allowed_versions=allowed)
    tab = read_skin_slots(data, sk)
    slot_names = [sk.joint_names[j] for j in tab]
    pos = read_positions(data, geo)
    nv = geo["vertex_count"]
    base = geo["bone_info_base"]

    by_name = {j.name.lower(): j for j in sk.joints}
    hi = by_name[HEAD.lower()].index
    ni = by_name[NECK.lower()].index
    if head_y is None and head_z is None:
        nloc = fk({i: local_matrix(sk.joints[i]) for i in range(sk.joint_count)}, sk.joints, sk.joint_count)
        print("== %s（不改骨架）" % (label or Path(path).name))
    else:
        print("== %s（模拟把 %s 枢轴下移：local y %.4f→%.4f, z %.4f→%.4f）"
              % (label or Path(path).name, HEAD,
                 sk.joints[hi].translation[1], head_y if head_y is not None else sk.joints[hi].translation[1],
                 sk.joints[hi].translation[2], head_z if head_z is not None else sk.joints[hi].translation[2]))

    rot_set = set()
    if rotate:
        for nm in rotate:
            for j in sk.joints:
                if j.name.lower() == nm.lower():
                    rot_set.add(j.index)
        missing = [nm for nm in rotate
                   if not any(j.name.lower() == nm.lower() for j in sk.joints)]
        if missing:
            raise ManualReviewRequired("骨架里没有骨 %s" % missing)
    else:
        rot_set = {hi}

    def build_pose(with_rot):
        loc = {}
        for i in range(sk.joint_count):
            m = local_matrix(sk.joints[i])
            if i in rot_set and with_rot:
                m = hna._mat_mul(rot4(axis, deg), m)
            if i == hi:
                if head_y is not None:
                    m[13] = head_y
                if head_z is not None:
                    m[14] = head_z
            loc[i] = m
        return fk(loc, sk.joints, sk.joint_count)

    w_bind = build_pose(False)
    w_pose = build_pose(True)
    # 自检：绕自身原点旋转 ⇒ 头骨关节的世界位置不变（只改朝向）
    for _j in rot_set:
        dt = max(abs(a - b) for a, b in zip(w_bind[_j][12:15], w_pose[_j][12:15]))
        if dt > 1e-6:
            raise ManualReviewRequired("自检失败：旋转不在 %s 自身原点上（Δ=%.2e）"
                                       % (sk.joints[_j].name, dt))

    skin = {i: hna._mat_mul(inv_affine(w_bind[i]), w_pose[i]) for i in range(sk.joint_count)}
    changed = set()
    stack = list(rot_set)
    kids = {}
    for j in sk.joints:
        kids.setdefault(j.parent_index, []).append(j.index)
    while stack:
        c = stack.pop()
        changed.add(c)
        stack.extend(kids.get(c, []))

    hw = w_bind[hi]
    head_pos = (hw[12], hw[13], hw[14])
    nw = w_bind[ni]
    neck_pos = (nw[12], nw[13], nw[14])
    y_neck, y_head = neck_pos[1], head_pos[1]

    regions = {"头部(含脸) y>=颈+7.5cm": [], "颈顶带 (颈+3.5~7.5cm)": [], "颈下带 (颈~颈+3.5cm)": [],
               "领口/上胸 (颈-8~颈 cm)": [], "头部刚性顶点(参考)": []}
    prof = {}          # --crease：y 分箱 -> [位移向量列表]
    dxbins = {}        # --centerline：y 分箱 -> {"ox":原x和, "nx":变形后x和, "n":个数}
    for v in range(nv):
        off = base + v * BONE_ELEM_SIZE
        idx = data[off:off + 8]
        w = data[off + 8:off + 16]
        tot = sum(w)
        if tot == 0:
            continue
        acc = [0.0, 0.0, 0.0]
        rigid_head = False
        for k in range(N_INFLUENCE):
            if w[k] == 0:
                continue
            j = tab[idx[k]]
            ww = w[k] / tot
            if j in changed:
                p = pos[v]
                m = skin[j]
                q = (p[0] * m[0] + p[1] * m[4] + p[2] * m[8] + m[12],
                     p[0] * m[1] + p[1] * m[5] + p[2] * m[9] + m[13],
                     p[0] * m[2] + p[1] * m[6] + p[2] * m[10] + m[14])
                acc[0] += ww * (q[0] - p[0])
                acc[1] += ww * (q[1] - p[1])
                acc[2] += ww * (q[2] - p[2])
            if j == hi and w[k] >= 250:
                rigid_head = True
        d = math.sqrt(acc[0] ** 2 + acc[1] ** 2 + acc[2] ** 2)
        if dom_in is not None:
            best, bw = -1, -1
            for k in range(N_INFLUENCE):
                if w[k] > bw:
                    best, bw = k, w[k]
            if best < 0 or slot_names[idx[best]].lower() not in dom_in:
                continue
        x, y, z = pos[v]
        r = math.dist((x, y, z), (neck_pos[0], y, neck_pos[2]))
        if crease and r < 0.09:
            bi = int(math.floor(y / binw))
            prof.setdefault(bi, []).append((acc[0], acc[1], acc[2], d))
        if centerline and r < 0.09:
            bi = int(math.floor(y / binw))
            rec = dxbins.setdefault(bi, {"ox": 0.0, "nx": 0.0, "n": 0, "ax": []})
            rec["ox"] += x
            rec["nx"] += x + acc[0]
            rec["n"] += 1
            rec["ax"].append(abs(acc[0]))
        if rigid_head:
            regions["头部刚性顶点(参考)"].append(d)
        # 区域一律锚在 **颈骨**（不随枢轴变体移动），保证跨变体/跨包可比
        if y >= y_neck + 0.075 and r >= 0.09:
            regions["头部(含脸) y>=颈+7.5cm"].append(d)
        elif y_neck + 0.035 <= y < y_neck + 0.075 and r < 0.09:
            regions["颈顶带 (颈+3.5~7.5cm)"].append(d)
        elif y_neck <= y < y_neck + 0.035 and r < 0.09:
            regions["颈下带 (颈~颈+3.5cm)"].append(d)
        elif y_neck - 0.08 <= y < y_neck and r < 0.15:
            regions["领口/上胸 (颈-8~颈 cm)"].append(d)

    print("   头骨枢轴 (%.4f, %.4f, %.4f) ｜ %s (%.4f, ...) ｜ 局部平移 y=%.4f z=%.4f"
          % (head_pos[0], head_pos[1], head_pos[2], NECK, neck_pos[1],
             sk.joints[hi].translation[1], sk.joints[hi].translation[2]))
    ref = pct(regions["头部刚性顶点(参考)"], 0.5) or 1e-9
    print("   区域                    顶点     中位位移cm   最大cm   相对头壳拖动")
    out = {"label": label or Path(path).name, "head_pivot": list(head_pos),
           "head_local": [round(sk.joints[hi].translation[1], 5), round(sk.joints[hi].translation[2], 5)],
           "deg": deg, "axis": axis, "regions": {}}
    for name, ds in regions.items():
        med, mx = pct(ds, 0.5) * 100, pct(ds, 1.0) * 100
        print("   %-22s %6d %10.3f %9.3f %13.2f"
              % (name, len(ds), med, mx, (pct(ds, 0.5) / ref) if ds else 0.0))
        out["regions"][name] = {"n": len(ds), "median_cm": med, "max_cm": mx}
    if crease and prof:
        print("   y 分箱（bin %.4f；只含到颈轴 r<0.09 的顶点）" % binw)
        print("   %-15s %5s %10s %10s %12s %s" % ("y", "顶点", "平均|位移|", "位移向量模", "与上层跳变", "备注"))
        prev = None
        prev_bi = None
        jumps = []
        for bi in sorted(prof):
            g = prof[bi]
            n = len(g)
            mx_abs = sum(t[3] for t in g) / n
            vb = (sum(t[0] for t in g) / n, sum(t[1] for t in g) / n, sum(t[2] for t in g) / n)
            vm = math.sqrt(sum(c * c for c in vb))
            j = None
            if prev is not None and prev_bi is not None and bi == prev_bi + 1:
                # 只统计**相邻**分箱之间的跳变；空箱会拉开采样间距，跨空箱的差值是假象
                j = math.dist(vb, prev)
                jumps.append((j, bi * binw))
            prev = vb
            prev_bi = bi
            flag = ""
            if j is not None and len(jumps) >= 3:
                med_j = sorted(x[0] for x in jumps)[len(jumps) // 2] or 1e-9
                if j >= 2.0 * med_j:
                    flag = "  <== 跳变大"
            print("   [%.4f,%.4f) %5d %10.4f %10.4f %12s %s"
                  % (bi * binw, (bi + 1) * binw, n, mx_abs * 100, vm * 100,
                     ("%.4f" % (j * 100)) if j is not None else "—", flag))
        if jumps:
            js = sorted(x[0] for x in jumps)
            med = js[len(js) // 2] or 1e-9
            mx = max(jumps)
            print("   跳变统计：中位 %.4f cm ｜ 最大 %.4f cm（@ y≈%.4f）｜ 最大/中位 = %.2f"
                  % (med * 100, mx[0] * 100, mx[1], mx[0] / med))
            out["crease"] = {"max_jump_cm": mx[0] * 100, "max_jump_y": mx[1],
                             "median_jump_cm": med * 100, "ratio": mx[0] / med}
    if centerline and dxbins:
        w_lo = neck_pos[1] - 0.01
        w_hi = neck_pos[1] + 0.075
        split = w_lo + 0.25 * (w_hi - w_lo)
        print("   %s" % ("颈部中心线 center_x(y)（变形后；bin %.4f；到颈轴 r<0.09）" % binw))
        print("   %-15s %5s %10s %10s %10s %9s" % ("y", "顶点", "原center_x", "变形center_x", "Δx", "平均|Δx|"))
        pts = []
        for bi in sorted(dxbins):
            g = dxbins[bi]
            if g["n"] == 0:
                continue
            yc = bi * binw
            oc, nc = g["ox"] / g["n"], g["nx"] / g["n"]
            print("   [%.4f,%.4f) %5d %10.5f %10.5f %+10.5f %9.5f"
                  % (yc, yc + binw, g["n"], oc, nc, nc - oc, sum(g["ax"]) / g["n"]))
            pts.append((yc, nc))
        if len(pts) >= 3:
            def ang(y0, y1):
                seg = [(y, x) for y, x in pts if y0 <= y <= y1]
                if len(seg) < 2:
                    return None
                dy = seg[-1][0] - seg[0][0]
                dx = seg[-1][1] - seg[0][1]
                return math.degrees(math.atan2(dx, dy)) if dy else None
            ra = ang(w_lo, split)
            ua = ang(split, w_hi)
            print("   颈根下 1/4 倾角 root_angle = %s° ｜ 上 3/4 倾角 upper_angle = %s°"
                  % ("%.3f" % ra if ra is not None else "n/a",
                     "%.3f" % ua if ua is not None else "n/a"))
            out["centerline"] = {"root_angle_deg": ra, "upper_angle_deg": ua,
                                 "window": [w_lo, w_hi], "split": split,
                                 "points": pts,
                                 # Δx = 变形后该层 x 均值 − 原 x 均值（无偏：同一顶点集，免疫采样偏置）
                                 "dx": [(bi * binw, dxbins[bi]["nx"] / dxbins[bi]["n"]
                                         - dxbins[bi]["ox"] / dxbins[bi]["n"], dxbins[bi]["n"])
                                        for bi in sorted(dxbins) if dxbins[bi]["n"]]}
    print()
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="头骨旋转 → 皮肤拖动量的离线预测（只读）")
    ap.add_argument("mesh", nargs="+")
    ap.add_argument("--label", action="append", default=[])
    ap.add_argument("--deg", type=float, default=15.0)
    ap.add_argument("--axis", default="roll", choices=("roll", "yaw", "pitch"))
    ap.add_argument("--head-local-y", type=float, default=None,
                    help="模拟把 Head_00 的局部平移 y 改成该值（同时改绑定与运行时骨架）")
    ap.add_argument("--head-local-z", type=float, default=None)
    ap.add_argument("--rotate", action="append", default=[],
                    help="额外旋转的骨名（大小写不敏感），可重复；与 --deg/--axis 一起用。"
                         "用于量「锁骨/其它骨一动，颈部皮肤被拽多少」，默认只旋 Head_00")
    ap.add_argument("--centerline", action="store_true",
                    help="输出变形后颈部**中心线** center_x(y) 与带符号 Δx，"
                         "并给出「颈根下 1/4」与「上 3/4」的中心线倾角（度）。"
                         "用于直接量化\"下段向右倾、上段竖直\"这类方向性症状")
    ap.add_argument("--crease", action="store_true",
                    help="沿颈高逐 y 分箱统计平均位移，并报告相邻层之间的**跳变量**"
                         "（折痕指标：权重硬切会在姿态下折出棱，而渐变不会）")
    ap.add_argument("--binw", type=float, default=0.004, help="--crease 的分箱高度（默认 0.004）")
    ap.add_argument("--dom-in", default=None,
                    help="只统计主导骨在该逗号列表内的顶点（大小写不敏感）。"
                         "用于排除头发/耳朵等装饰件对颈/领口带 max 的污染，例如 "
                         "--dom-in Neck_00,Spine_01,Spine_00,Head_00")
    ap.add_argument("--json")
    args = ap.parse_args(argv)

    reps = []
    for i, m in enumerate(args.mesh):
        label = args.label[i] if i < len(args.label) else Path(m).name
        try:
            dom_in = ({s.strip().lower() for s in args.dom_in.split(",") if s.strip()}
                      if args.dom_in else None)
            reps.append(analyse(m, args.deg, args.axis, args.head_local_y, args.head_local_z,
                                label, dom_in, args.crease, args.binw, tuple(args.rotate),
                                args.centerline))
        except ManualReviewRequired as exc:
            print("!! %s：MANUAL_REVIEW_REQUIRED %s\n" % (label, exc))
    if args.json:
        p = Path(args.json)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"axis": args.axis, "deg": args.deg, "reports": reps},
                                indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8", newline="\n")
        print("json: %s" % p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

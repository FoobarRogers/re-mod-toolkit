#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""骨架旋转与累积世界变换只读诊断 —— J018 头颈轴线 / 头肩比研究工具。

动机（`TODO_J018_HeadNeck_Axis_HeadShoulder_Ratio_Diagnosis.md` §1.2 / Step 2）：

    LuaBone 只表达 Translation（`f_shadow.json` 本身也只有 x/y/z），
    所以「Local Translation 已对齐」**不能**推出「头颈姿态正确」。
    必须同时看 Local Rotation 与 **累积世界变换**。

本工具对任意两个 MESH 骨架输出共同骨的：

    Local Translation delta   分量 + 模
    Local Rotation delta      轴角（度）+ 轴向量
    World Translation delta   FK 累积后的关节世界位置差
    World Rotation delta      FK 累积后的世界朝向夹角

矩阵约定（与 `mesh_skeleton.py` 的记录布局一致）：

    64 字节记录 = 3x3 旋转（前 3 行，行主序）+ 平移（第 4 行）
    即 [ R00 R01 R02 0 / R10 R11 R12 0 / R20 R21 R22 0 / Tx Ty Tz 1 ]
    → 行向量约定，点的世界位置 = p · Local · ParentWorld
    → W(child) = Local(child) × W(parent)，骨骼世界位置 = W 的平移行

**只读、可重放、不修改任何资源**，不参与 Phase F 生产 LuaBone 生成。
需要解析尚未进入生产门禁的 mesh 版本时，显式传 `--allow-version`。
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mesh_skeleton import (  # noqa: E402
    SUPPORTED_MESH_VERSION,
    ManualReviewRequired,
    load_mesh_skeleton,
)

# 头颈主轴 + 玩家/面部特殊骨（TODO §3 A1 要求的核对清单）
FOCUS_BONES = (
    "Root", "Cog", "Waist_00", "Spine_00", "Spine_01", "Neck_00", "Neck_00_S",
    "Head_00", "Face_Parts", "Jaw_00", "LookAt", "PL_Cam",
    "L_Foot_IK", "R_Foot_IK", "L_Hand_IK", "R_Hand_IK",
)

# float32 精度噪声在 acos 上被放大成 ~0.02 度（见 §判读），
# 因此 < 0.05 度一律视为「与浮点噪声不可区分」。
ROT_NOISE_DEG = 0.05
ROT_BUCKETS = ((ROT_NOISE_DEG, "=<noise"), (0.5, ">0.5deg"), (2.0, ">2deg"), (5.0, ">5deg"))

T_BUCKETS = ((0.001, ">1mm"), (0.01, ">1cm"), (0.02, ">2cm"), (0.05, ">5cm"))

# 父链递归的防环上限
_MAX_DEPTH = 512


def _len3(v):
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _local_matrix(joint):
    """把一条 joint record 变成 4x4 行主序局部矩阵。"""
    r = joint.rotation
    t = joint.translation
    return [
        r[0], r[1], r[2], 0.0,
        r[3], r[4], r[5], 0.0,
        r[6], r[7], r[8], 0.0,
        t[0], t[1], t[2], 1.0,
    ]


def _mat_mul(a, b):
    c = [0.0] * 16
    for i in range(4):
        ai = i * 4
        for j in range(4):
            c[ai + j] = (a[ai] * b[j] + a[ai + 1] * b[4 + j]
                         + a[ai + 2] * b[8 + j] + a[ai + 3] * b[12 + j])
    return c


def world_matrices(skeleton):
    """返回 {joint index: 4x4 世界矩阵}，行向量约定 W(child) = L(child) x W(parent)。"""
    memo = {}

    def walk(idx, depth):
        if idx in memo:
            return memo[idx]
        if depth > _MAX_DEPTH:
            raise ManualReviewRequired("骨层级深度超过 %d，疑似存在环" % _MAX_DEPTH)
        j = skeleton.joints[idx]
        local = _local_matrix(j)
        p = j.parent_index
        if 0 <= p < skeleton.joint_count and p != idx:
            w = _mat_mul(local, walk(p, depth + 1))
        else:
            w = local
        memo[idx] = w
        return w

    for j in skeleton.joints:
        walk(j.index, 0)
    return memo


def _world_pos(w):
    return (w[12], w[13], w[14])


def _world_rot(w):
    return (w[0], w[1], w[2], w[4], w[5], w[6], w[8], w[9], w[10])


def _rot_delta(a, b):
    """把 A 的朝向转到 B 的朝向：返回 (角度度, 轴向量)。

    R_d = A^T · B；夹角与轴取自 R_d 的轴角分解。角度无约定歧义。
    """
    at = (a[0], a[3], a[6], a[1], a[4], a[7], a[2], a[5], a[8])  # A 转置
    d = [
        at[0] * b[0] + at[1] * b[3] + at[2] * b[6],
        at[0] * b[1] + at[1] * b[4] + at[2] * b[7],
        at[0] * b[2] + at[1] * b[5] + at[2] * b[8],
        at[3] * b[0] + at[4] * b[3] + at[5] * b[6],
        at[3] * b[1] + at[4] * b[4] + at[5] * b[7],
        at[3] * b[2] + at[4] * b[5] + at[5] * b[8],
        at[6] * b[0] + at[7] * b[3] + at[8] * b[6],
        at[6] * b[1] + at[7] * b[4] + at[8] * b[7],
        at[6] * b[2] + at[7] * b[5] + at[8] * b[8],
    ]
    cos = max(-1.0, min(1.0, (d[0] + d[4] + d[8] - 1.0) / 2.0))
    ang = math.degrees(math.acos(cos))
    s = math.sin(math.radians(ang))
    if abs(s) < 1e-9:
        return ang, (0.0, 0.0, 0.0)
    axis = ((d[7] - d[5]) / (2 * s), (d[2] - d[6]) / (2 * s), (d[3] - d[1]) / (2 * s))
    return ang, axis


def _orthonormality_error(m):
    """世界矩阵左上 3x3 的行范数最大偏差 —— FK 实现的自校验。"""
    worst = 0.0
    for r in range(3):
        n = math.sqrt(sum(m[r * 4 + c] ** 2 for c in range(3)))
        worst = max(worst, abs(n - 1.0))
    return worst


def _median(xs):
    if not xs:
        return 0.0
    n = len(xs)
    return xs[n // 2] if n % 2 else 0.5 * (xs[n // 2 - 1] + xs[n // 2])


def _chain(skeleton, name):
    return skeleton.hierarchy_chain(name)


def analyse(path_a, label_a, path_b, label_b, allowed_versions=None):
    sk_a = load_mesh_skeleton(path_a, allowed_versions=allowed_versions)
    sk_b = load_mesh_skeleton(path_b, allowed_versions=allowed_versions)
    wa = world_matrices(sk_a)
    wb = world_matrices(sk_b)

    if sk_a.joint_count != len(wa) or sk_b.joint_count != len(wb):
        raise ManualReviewRequired("世界矩阵覆盖不全，FK 累积未覆盖全部关节")

    ia = {j.name.lower(): j for j in sk_a.joints}
    ib = {j.name.lower(): j for j in sk_b.joints}
    common = sorted(set(ia) & set(ib))

    rows = []
    for key in common:
        ja, jb = ia[key], ib[key]
        wja, wjb = wa[ja.index], wb[jb.index]
        dt = _sub(jb.translation, ja.translation)
        lt_ang, lt_axis = _rot_delta(ja.rotation, jb.rotation)
        wt_ang, wt_axis = _rot_delta(_world_rot(wja), _world_rot(wjb))
        dwt = _sub(_world_pos(wjb), _world_pos(wja))
        rows.append({
            "bone": ja.name,
            "name_in_b": jb.name,
            "index_a": ja.index,
            "index_b": jb.index,
            "parent_a": sk_a.joints[ja.parent_index].name if 0 <= ja.parent_index < sk_a.joint_count else None,
            "parent_b": sk_b.joints[jb.parent_index].name if 0 <= jb.parent_index < sk_b.joint_count else None,
            "local_t_a": list(ja.translation),
            "local_t_b": list(jb.translation),
            "local_t_delta": list(dt),
            "local_t_delta_len": _len3(dt),
            "local_rot_deg": lt_ang,
            "local_rot_axis": list(lt_axis),
            "world_t_a": list(_world_pos(wja)),
            "world_t_b": list(_world_pos(wjb)),
            "world_t_delta": list(dwt),
            "world_t_delta_len": _len3(dwt),
            "world_rot_deg": wt_ang,
            "world_rot_axis": list(wt_axis),
        })

    t_lens = sorted(r["local_t_delta_len"] for r in rows)
    wt_lens = sorted(r["world_t_delta_len"] for r in rows)
    l_rots = sorted(r["local_rot_deg"] for r in rows)
    w_rots = sorted(r["world_rot_deg"] for r in rows)

    stats = {
        "common_joint_count": len(rows),
        "median_local_t_delta": _median(t_lens),
        "max_local_t_delta": t_lens[-1] if t_lens else 0.0,
        "max_local_t_delta_bone": max(rows, key=lambda r: r["local_t_delta_len"])["bone"] if rows else None,
        "median_world_t_delta": _median(wt_lens),
        "max_world_t_delta": wt_lens[-1] if wt_lens else 0.0,
        "max_world_t_delta_bone": max(rows, key=lambda r: r["world_t_delta_len"])["bone"] if rows else None,
        "median_local_rot_deg": _median(l_rots),
        "max_local_rot_deg": l_rots[-1] if l_rots else 0.0,
        "max_local_rot_deg_bone": max(rows, key=lambda r: r["local_rot_deg"])["bone"] if rows else None,
        "median_world_rot_deg": _median(w_rots),
        "max_world_rot_deg": w_rots[-1] if w_rots else 0.0,
        "max_world_rot_deg_bone": max(rows, key=lambda r: r["world_rot_deg"])["bone"] if rows else None,
        "local_rot_at_noise_level": sum(1 for x in l_rots if x <= ROT_NOISE_DEG),
        "world_rot_at_noise_level": sum(1 for x in w_rots if x <= ROT_NOISE_DEG),
        "fk_orthonormality_error_a": max(_orthonormality_error(m) for m in wa.values()),
        "fk_orthonormality_error_b": max(_orthonormality_error(m) for m in wb.values()),
    }
    for thr, label in T_BUCKETS:
        stats["local_count_" + label] = sum(1 for x in t_lens if x > thr)
        stats["world_count_" + label] = sum(1 for x in wt_lens if x > thr)
    for thr, label in ROT_BUCKETS[1:]:
        stats["count_local_rot_" + label] = sum(1 for x in l_rots if x > thr)
        stats["count_world_rot_" + label] = sum(1 for x in w_rots if x > thr)

    focus = [r for r in rows if r["bone"] in FOCUS_BONES]

    return {
        "a": {"label": label_a, "path": sk_a.source, "version": "0x%08X" % sk_a.version,
              "size": sk_a.file_size, "joint_count": sk_a.joint_count,
              "material_names": sk_a.material_names},
        "b": {"label": label_b, "path": sk_b.source, "version": "0x%08X" % sk_b.version,
              "size": sk_b.file_size, "joint_count": sk_b.joint_count,
              "material_names": sk_b.material_names},
        "a_only": sorted(ia[k].name for k in set(ia) - set(ib)),
        "b_only": sorted(ib[k].name for k in set(ib) - set(ia)),
        "stats": stats,
        "focus_bones": focus,
        "rotations_over_noise": sorted(
            [{"bone": r["bone"], "local_rot_deg": r["local_rot_deg"], "world_rot_deg": r["world_rot_deg"],
              "local_rot_axis": r["local_rot_axis"], "world_t_delta_len": r["world_t_delta_len"]}
             for r in rows if r["local_rot_deg"] > ROT_NOISE_DEG or r["world_rot_deg"] > ROT_NOISE_DEG],
            key=lambda r: -r["local_rot_deg"]),
        "top_world_t_delta": sorted(
            [{"bone": r["bone"], "world_t_delta_len": r["world_t_delta_len"],
              "world_t_delta": r["world_t_delta"], "world_rot_deg": r["world_rot_deg"],
              "local_t_delta_len": r["local_t_delta_len"]} for r in rows],
            key=lambda r: -r["world_t_delta_len"])[:25],
        "chains": {
            "a_head_chain": _chain(sk_a, "Head_00"),
            "b_head_chain": _chain(sk_b, "Head_00"),
            "a_neck_s_parent": sk_a.parent_of("Neck_00_S"),
            "b_neck_s_parent": sk_b.parent_of("Neck_00_S"),
            "a_neck_s_children": sk_a.children_of("Neck_00_S"),
            "b_neck_s_children": sk_b.children_of("Neck_00_S"),
        },
        "joints": sorted(rows, key=lambda r: -r["local_t_delta_len"]),
    }


def render_md(report):
    s = report["stats"]
    L = []
    L.append("# %s vs %s —— 骨架平移 / 旋转 / 累积世界变换" % (
        report["a"]["label"], report["b"]["label"]))
    L.append("")
    L.append("| | A (%s) | B (%s) |" % (report["a"]["label"], report["b"]["label"]))
    L.append("| --- | --- | --- |")
    L.append("| path | `%s` | `%s` |" % (report["a"]["path"], report["b"]["path"]))
    L.append("| MESH version | %s | %s |" % (report["a"]["version"], report["b"]["version"]))
    L.append("| size | %d | %d |" % (report["a"]["size"], report["b"]["size"]))
    L.append("| joint_count | %d | %d |" % (report["a"]["joint_count"], report["b"]["joint_count"]))
    L.append("")
    L.append("## 统计（共同 joint = %d）" % s["common_joint_count"])
    L.append("")
    L.append("```text")
    L.append("Local  T delta  median %.6f  max %.6f (%s)" % (
        s["median_local_t_delta"], s["max_local_t_delta"], s["max_local_t_delta_bone"]))
    L.append("World  T delta  median %.6f  max %.6f (%s)" % (
        s["median_world_t_delta"], s["max_world_t_delta"], s["max_world_t_delta_bone"]))
    L.append("Local  R delta  median %.4f deg  max %.4f deg (%s)" % (
        s["median_local_rot_deg"], s["max_local_rot_deg"], s["max_local_rot_deg_bone"]))
    L.append("World  R delta  median %.4f deg  max %.4f deg (%s)" % (
        s["median_world_rot_deg"], s["max_world_rot_deg"], s["max_world_rot_deg_bone"]))
    L.append("")
    L.append("Local R 在噪声级(<=%.2f deg): %d / %d" % (
        ROT_NOISE_DEG, s["local_rot_at_noise_level"], s["common_joint_count"]))
    L.append("World R 在噪声级(<=%.2f deg): %d / %d" % (
        ROT_NOISE_DEG, s["world_rot_at_noise_level"], s["common_joint_count"]))
    L.append("Local R >0.5deg = %d   >2deg = %d   >5deg = %d" % (
        s["count_local_rot_>0.5deg"], s["count_local_rot_>2deg"], s["count_local_rot_>5deg"]))
    L.append("World R >0.5deg = %d   >2deg = %d   >5deg = %d" % (
        s["count_world_rot_>0.5deg"], s["count_world_rot_>2deg"], s["count_world_rot_>5deg"]))
    L.append("")
    L.append("FK 自校验 世界矩阵行范数最大偏差: A %.3e  B %.3e" % (
        s["fk_orthonormality_error_a"], s["fk_orthonormality_error_b"]))
    L.append("```")
    L.append("")
    L.append("## 头颈与特殊骨")
    L.append("")
    L.append("| bone | LocalT A | LocalT B | |ΔLocalT| | ΔLocalR° | ΔWorldT | |ΔWorldT| | ΔWorldR° |")
    L.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in report["focus_bones"]:
        ta, tb = r["local_t_a"], r["local_t_b"]
        wd = r["world_t_delta"]
        L.append("| `%s` | (%.6g, %.6g, %.6g) | (%.6g, %.6g, %.6g) | %.6f | %.4f | (%.4g, %.4g, %.4g) | %.6f | %.4f |" % (
            r["bone"], ta[0], ta[1], ta[2], tb[0], tb[1], tb[2],
            r["local_t_delta_len"], r["local_rot_deg"],
            wd[0], wd[1], wd[2], r["world_t_delta_len"], r["world_rot_deg"]))
    L.append("")
    L.append("## 旋转超出浮点噪声的骨（local 或 world > %.2f deg）" % ROT_NOISE_DEG)
    L.append("")
    if not report["rotations_over_noise"]:
        L.append("```text")
        L.append("(无 —— 全部共同骨的两侧旋转在浮点噪声内一致)")
        L.append("```")
    else:
        L.append("| bone | ΔLocalR° | ΔWorldR° | local 轴 | |ΔWorldT| |")
        L.append("| --- | --- | --- | --- | --- |")
        for r in report["rotations_over_noise"]:
            ax = r["local_rot_axis"]
            L.append("| `%s` | %.4f | %.4f | (%.4f, %.4f, %.4f) | %.6f |" % (
                r["bone"], r["local_rot_deg"], r["world_rot_deg"], ax[0], ax[1], ax[2],
                r["world_t_delta_len"]))
    L.append("")
    L.append("## 世界位置差 Top 25")
    L.append("")
    L.append("| # | bone | ΔWorldT | |ΔWorldT| | ΔWorldR° | |ΔLocalT| |")
    L.append("| --- | --- | --- | --- | --- | --- |")
    for i, r in enumerate(report["top_world_t_delta"], 1):
        d = r["world_t_delta"]
        L.append("| %d | `%s` | (%.5g, %.5g, %.5g) | %.6f | %.4f | %.6f |" % (
            i, r["bone"], d[0], d[1], d[2], r["world_t_delta_len"], r["world_rot_deg"],
            r["local_t_delta_len"]))
    L.append("")
    L.append("## 头颈层级与叶子骨")
    L.append("")
    L.append("```text")
    L.append("A Head_00 链 : %s" % " -> ".join(report["chains"]["a_head_chain"] or []))
    L.append("B Head_00 链 : %s" % " -> ".join(report["chains"]["b_head_chain"] or []))
    L.append("A Neck_00_S 父/子 : %s / %s" % (
        report["chains"]["a_neck_s_parent"], report["chains"]["a_neck_s_children"]))
    L.append("B Neck_00_S 父/子 : %s / %s" % (
        report["chains"]["b_neck_s_parent"], report["chains"]["b_neck_s_children"]))
    L.append("```")
    L.append("")
    L.append("## A_only (%d)" % len(report["a_only"]))
    L.append("")
    L.append("```text")
    L.append(", ".join(report["a_only"]) or "(none)")
    L.append("```")
    L.append("")
    L.append("## B_only (%d)" % len(report["b_only"]))
    L.append("")
    L.append("```text")
    L.append(", ".join(report["b_only"]) or "(none)")
    L.append("```")
    L.append("")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="骨架旋转 / 累积世界变换只读对照（J018 头颈轴线诊断）")
    ap.add_argument("mesh_a")
    ap.add_argument("mesh_b")
    ap.add_argument("--label-a", default="A")
    ap.add_argument("--label-b", default="B")
    ap.add_argument("--allow-version", action="append", default=[],
                    help="研究用：额外放开的 MESH version（如 0x0141D2B8），可重复")
    ap.add_argument("--json")
    ap.add_argument("--md")
    args = ap.parse_args(argv)

    allowed = None
    if args.allow_version:
        allowed = (SUPPORTED_MESH_VERSION,) + tuple(int(v, 0) for v in args.allow_version)

    try:
        report = analyse(args.mesh_a, args.label_a, args.mesh_b, args.label_b,
                         allowed_versions=allowed)
    except ManualReviewRequired as exc:
        print("MANUAL_REVIEW_REQUIRED")
        print("  " + str(exc))
        return 2

    if args.json:
        p = Path(args.json)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    if args.md:
        p = Path(args.md)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(render_md(report))

    s = report["stats"]
    print("%s vs %s : common=%d" % (report["a"]["label"], report["b"]["label"],
                                    s["common_joint_count"]))
    print("  LocalT  median %.6f  max %.6f (%s)" % (
        s["median_local_t_delta"], s["max_local_t_delta"], s["max_local_t_delta_bone"]))
    print("  WorldT  median %.6f  max %.6f (%s)" % (
        s["median_world_t_delta"], s["max_world_t_delta"], s["max_world_t_delta_bone"]))
    print("  LocalR  median %.4f  max %.4f (%s)" % (
        s["median_local_rot_deg"], s["max_local_rot_deg"], s["max_local_rot_deg_bone"]))
    print("  WorldR  median %.4f  max %.4f (%s)" % (
        s["median_world_rot_deg"], s["max_world_rot_deg"], s["max_world_rot_deg_bone"]))
    print("  FK 自校验 行范数偏差 A=%.3e B=%.3e" % (
        s["fk_orthonormality_error_a"], s["fk_orthonormality_error_b"]))
    if args.json:
        print("  json: %s" % args.json)
    if args.md:
        print("  md  : %s" % args.md)
    return 0


if __name__ == "__main__":
    sys.exit(main())

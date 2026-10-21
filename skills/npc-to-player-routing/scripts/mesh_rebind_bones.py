#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MESH 顶点权重改写：把子骨的蒙皮权重并入父骨（**等长改写**，只动 BoneInfo 字节）。

这个文件做两件事：**只读判定**（哪些权重归属有问题）与**等长改写**（重新分配权重）。
判定本身比改写重要 —— 判错骨身份就会把好的部件改坏（v0.1 的教训见下）。

为什么是安全改写
----------------
* 只替换 BoneInfo 元素里的骨索引与权重量化值，**文件长度与所有段偏移不变**；
* 实测每顶点权重和恒为 255（min 254 / max 256），所以"子骨权重加到父骨"是
  **权重守恒的重新分配**，不会溢出，也不需要归一化；
* 空槽位由 `w == 0` 标记（idx 保留残余值但无意义），可安全复用。

格式（依据社区实现 Blender-RE-Engine-Model / REEMeshFile.py，本项目已逐字段对账）
--------------------------------------------------------------------------------
    Header(128 B) @0
        +80  vertexBufferHeaderOffset (u64)
    GeometryBuffersHeader @vertexBufferHeaderOffset
        +0   vertexElementHeadersOffset (u64)
        +8   vertexBufferOffset (u64)
        +16  faceIndexBufferOffset (u64)
        +32  vertexElementCount (i16 x2)
    VertexElementHeader（每条 8 B，共 vertexElementCount[1] 条）
        +0  elementType (i16)  0=Position 1=NormalsTangents 2=UV0 3=UV1 4=BoneInfo
        +2  bytesPerVertex (i16)
        +4  offsetInVertexBuffer (u32)
    顶点数 = 某元素的 offsetInVertexBuffer / 它之前所有元素的 bytesPerVertex 之和
    BoneInfo（每顶点 16 B）
        +0  8 x u8 **槽位下标**（见下）
        +8  8 x u8 权重（w / 255）

**骨索引的语义（2026-09-26 修正，v0.2）**
----------------------------------------
那 8 个 u8 **不是关节数组下标**，而是 armature 头部里一张**蒙皮槽位表**的下标：

    S = u64@0x30（armature 头偏移）
    S+0x00  u32  关节数 joint_count
    S+0x04  u32  蒙皮槽位数 slot_count
    S+0x10  u64  parent 数组偏移
    S+0x18  u64  关节记录（64 B/条）数组偏移
    S+0x30  u16 x slot_count   槽位 -> 关节 下标表（递增子序列）

三份 mesh 实测：npc709 140/76、Golden JRwst017 118/73、玩家外观 pl244 178/140。
按此表映射后"槽位顶点质心 ↔ 骨世界位置"中位距离 0.03~0.05（肢体分段几何自洽）。

**v0.1 的错误与后果（已实机确认）**
-----------------------------------
v0.1 把 u8 当关节下标，于是把 `Jaw_00 / helm_chain_*` 认成 #21~#24 并"并入 Head_00"；
真实身份是槽位 21~24 = `R_Hair_02 / R_Hair_03 / Chain_00 / front_Chain_00`，
目标是槽位 20 = `R_Hair_01`。实机表现为**刘海被拉成一根尖刺**
（刘海由 `front_Chain_00` 驱动，被并到了受物理解算驱动的发骨上），
而领口/颈根症状毫无变化。该包已作废，见 `dist/minimal-validation/_broken/`。

**修正后的判据（v0.2）**
------------------------
"寄生骨"的判据不是"父链上能否找到玩家骨"，而是：

    slot 名不在**玩家骨架**里 ⇒ 该骨在 player 侧无人驱动，区域刚性冻结；
    若它的顶点还与玩家骨**混合蒙皮**（两边权重都显著）⇒ 交界处被撕裂 = 可见剪切。

玩家骨架用横向证据判定（78 个 `[outfilter]` 玩家外观 mesh 的骨名出现率 ≥80%）：
`Chain_00`/`front_Chain_00`/`L_Hair_*`/`L_Ear_*`/`L_Oupai_*`/`Ribbon_00`/`L_plus*`/`Chain_Tail_*`
出现率只有 0~5%（那几例正是 NPC 转玩家的包）⇒ 它们**不是**玩家骨，而是源模型自带的装饰骨。

**第二类问题：顶点被错挂在某根玩家骨上**（J018 test4/test5 实证）

判据是"某骨的顶点区域在解剖学上不属于它"，用横向比对定标：
`Head_00` 身体区最低 y − `Neck_00` y 在三个正常包为 +0.023~+0.031，npc709 是 −0.074（颈下多了
一块 108 顶点的领口前片）；进一步看颈柱几何的 `Head_00` 占比，三个正常包 0~21%、
npc709 68%（整根颈肉挂在头骨上）。

修法用 `--map 子骨:父骨` + 区域限定，并且**优先用 `--ramp-y FULL:ZERO` 做渐变**而不是硬切：
正常包的颈柱本身就是"颈骨→头骨"的混合权重，硬切会在平滑表面留下折痕。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mesh_skeleton import (  # noqa: E402
    SUPPORTED_MESH_VERSION,
    ManualReviewRequired,
    parse_mesh_skeleton,
)

MESH_MAGIC = b"MESH"
ELEM_POSITION, ELEM_NORMALS, ELEM_UV0, ELEM_UV1, ELEM_BONE = 0, 1, 2, 3, 4
N_INFLUENCE = 8
BONE_ELEM_SIZE = 16


def _u64(data, off):
    return struct.unpack_from("<Q", data, off)[0]


def locate_geometry(data, allowed_versions):
    """解析 GeometryBuffersHeader 与顶点元素表，返回定位信息。

    只做结构校验，不做语义推断；命中不一致一律 STOP。
    """
    size = len(data)
    if data[:4] != MESH_MAGIC:
        raise ManualReviewRequired("MESH magic 不匹配")
    version = struct.unpack_from("<I", data, 4)[0]
    accepted = (SUPPORTED_MESH_VERSION,) if allowed_versions is None else tuple(allowed_versions)
    if version not in accepted:
        raise ManualReviewRequired("MESH version 0x%08X 不在允许集合 %s"
                                   % (version, [hex(v) for v in accepted]))
    file_size = struct.unpack_from("<Q", data, 8)[0]
    if file_size != size:
        raise ManualReviewRequired("fileSize 字段 %d != 实际长度 %d" % (file_size, size))

    gh = _u64(data, 0x50)                      # Header.vertexBufferHeaderOffset
    if not (0x80 <= gh < size - 48):
        raise ManualReviewRequired("vertexBufferHeaderOffset 0x%X 越界" % gh)
    elem_hdr_off = _u64(data, gh + 0)
    vb_off = _u64(data, gh + 8)
    fb_off = _u64(data, gh + 16)
    elem_count = struct.unpack_from("<hh", data, gh + 32)[1]
    if not (0 < elem_count <= 32):
        raise ManualReviewRequired("vertexElementCount=%d 不合理" % elem_count)

    elems = []
    for i in range(elem_count):
        et, bpv, off = struct.unpack_from("<hhI", data, elem_hdr_off + i * 8)
        if et < 0 or bpv <= 0 or bpv > 256:
            continue                            # 尾部填充/垃圾条目
        elems.append((et, bpv, off))
    elems.sort(key=lambda x: x[2])

    bones = [e for e in elems if e[0] == ELEM_BONE]
    if not bones:
        raise ManualReviewRequired("顶点元素表里没有 BoneInfo（type=4）")
    _, bone_bpv, bone_off = bones[0]
    if bone_bpv != BONE_ELEM_SIZE:
        raise ManualReviewRequired("BoneInfo bytesPerVertex=%d，期望 %d" % (bone_bpv, BONE_ELEM_SIZE))

    prefix = sum(bpv for _, bpv, off in elems if off < bone_off)
    if prefix <= 0 or bone_off % prefix != 0:
        raise ManualReviewRequired("无法由元素布局推出顶点数（前缀字节 %d，BoneInfo off %d）"
                                   % (prefix, bone_off))
    vertex_count = bone_off // prefix
    if vertex_count <= 0:
        raise ManualReviewRequired("顶点数推算为 %d" % vertex_count)

    bone_base = vb_off + bone_off
    if bone_base + vertex_count * BONE_ELEM_SIZE > size:
        raise ManualReviewRequired("BoneInfo 区越界（base 0x%X + %d x 16 > 0x%X）"
                                   % (bone_base, vertex_count, size))
    return {
        "version": "0x%08X" % version, "size": size,
        "geometry_header": gh, "vertex_buffer": vb_off, "face_index_buffer": fb_off,
        "elements": [{"type": e, "bytes_per_vertex": b, "offset_in_vb": o} for e, b, o in elems],
        "bone_info_offset_in_vb": bone_off, "bone_info_base": bone_base,
        "vertex_count": vertex_count,
    }


def read_skin_slots(data, sk):
    """读 armature 头部的**蒙皮槽位表**，返回槽位下标 -> 关节下标。

    BoneInfo 里的 u8 是这张表的下标（v0.2 修正）。表本身是递增子序列，
    只包含"有权重的关节"。任何不一致一律 STOP —— 骨身份判错会把好部件改坏。
    """
    if sk.joint_count <= 0:
        raise ManualReviewRequired("关节数为 %d" % sk.joint_count)
    s = _u64(data, 0x30)
    if not (0x30 < s < len(data) - 0x38):
        raise ManualReviewRequired("armature 头偏移 0x%X 越界" % s)
    joint_count, slot_count = struct.unpack_from("<II", data, s)
    if joint_count != sk.joint_count:
        raise ManualReviewRequired("armature 关节数 %d != 解析出的 %d"
                                   % (joint_count, sk.joint_count))
    if not (0 < slot_count <= joint_count):
        raise ManualReviewRequired("蒙皮槽位数 %d 不合理（关节 %d）" % (slot_count, joint_count))
    tab_off = s + 0x30
    if tab_off + slot_count * 2 > len(data):
        raise ManualReviewRequired("槽位表越界")
    tab = struct.unpack_from("<%dH" % slot_count, data, tab_off)
    if max(tab) >= joint_count:
        raise ManualReviewRequired("槽位表含越界关节下标 %d" % max(tab))
    if len(set(tab)) != slot_count or tab != tuple(sorted(tab)):
        raise ManualReviewRequired("槽位表不是递增的唯一子序列")
    return tab


def read_positions(data, geo):
    """读出每顶点的绑定坐标（Position 元素，12 B/顶点）。"""
    pos_elem = [e for e in geo["elements"] if e["type"] == ELEM_POSITION]
    if not pos_elem or pos_elem[0]["bytes_per_vertex"] != 12:
        raise ManualReviewRequired("Position 元素缺失或步长不是 12")
    base = geo["vertex_buffer"] + pos_elem[0]["offset_in_vb"]
    nv = geo["vertex_count"]
    return [struct.unpack_from("<fff", data, base + v * 12) for v in range(nv)]


def scan_influences(data, geo):
    """统计每根骨驱动的顶点数与权重和（只读）。"""
    base, nv = geo["bone_info_base"], geo["vertex_count"]
    used = {}
    for v in range(nv):
        off = base + v * BONE_ELEM_SIZE
        idx = data[off:off + 8]
        w = data[off + 8:off + 16]
        for k in range(N_INFLUENCE):
            if w[k] == 0:
                continue
            rec = used.setdefault(idx[k], {"vertices": 0, "weight_sum": 0.0, "weight_max": 0.0})
            rec["vertices"] += 1
            rec["weight_sum"] += w[k] / 255.0
            rec["weight_max"] = max(rec["weight_max"], w[k] / 255.0)
    return used


def rebind(data, geo, mapping, allow=None, frac=None):
    """把 mapping `{子骨槽位: 父骨槽位}` 施加到 BoneInfo 上。返回统计。

    `allow(vertex_index) -> bool` 可选：只对通过筛选的顶点生效（区域限定）。
    `frac(vertex_index) -> float` 可选：**转移比例**（0~1），默认 1.0=整份转移。
    两者合起来支持"只把颈根到颌下这段的 Head_00 权重按高度渐变改挂到 Neck_00"
    这类定点手术 —— 渐变（而不是硬切）是为了不在平滑表面上留下新接缝。

    权重守恒：子骨槽位移出的量化值原样加到父骨槽位；若该顶点尚无父骨槽位，
    复用腾出来的空槽。每顶点权重和不变（比例按四舍五入取整后余数留在子骨）。
    """
    base, nv = geo["bone_info_base"], geo["vertex_count"]
    out = bytearray(data)
    stat = {
        "mapping": {str(k): v for k, v in mapping.items()},
        "vertices_touched": 0, "vertices_merged_into_existing": 0,
        "vertices_reused_slot": 0, "vertices_no_free_slot": 0, "vertices_skipped_no_slot": 0,
        "moved_weight_units": 0,
        "clipped_slots": 0,
        "weight_sum_before": [], "weight_sum_after": [],
    }
    changed_lo, changed_hi = None, None
    for v in range(nv):
        if allow is not None and not allow(v):
            continue
        t = 1.0 if frac is None else max(0.0, min(1.0, frac(v)))
        if t <= 0.0:
            continue
        off = base + v * BONE_ELEM_SIZE
        idx = list(out[off:off + 8])
        w = list(out[off + 8:off + 16])
        moved = 0
        victims = []
        for k in range(N_INFLUENCE):
            if idx[k] in mapping and w[k]:
                victims.append(k)
        if not victims:
            continue
        before = sum(w)
        by_parent = {}
        for k in victims:
            mv = int(round(w[k] * t))          # 比例转移；余数留在子骨，保证守恒
            if mv <= 0:
                continue
            by_parent.setdefault(mapping[idx[k]], []).append((k, mv))
        if not by_parent:
            continue
        # 需要为"父骨尚未出现在该顶点"的情况腾出槽位：空槽数（含整份转移腾出的槽）够才做，
        # 否则整个顶点跳过并回滚 —— 保证每顶点权重和不变。
        need_new = [p for p in by_parent
                    if not any(idx[k] == p and w[k] > 0 for k in range(N_INFLUENCE))]
        free_slots = sum(1 for k in range(N_INFLUENCE) if w[k] == 0)
        if len(need_new) > free_slots:
            stat["vertices_skipped_no_slot"] += 1
            continue
        for p, pairs in by_parent.items():
            mv = sum(x for _, x in pairs)
            for k, x in pairs:
                w[k] -= x
            moved += mv
            slot = next((k for k in range(N_INFLUENCE) if idx[k] == p and w[k] > 0), None)
            if slot is not None:
                w[slot] += mv
                stat["vertices_merged_into_existing"] += 1
            else:
                slot = next((k for k in range(N_INFLUENCE) if w[k] == 0), None)
                idx[slot] = p
                w[slot] = mv
                stat["vertices_reused_slot"] += 1
        stat["moved_weight_units"] += moved
        if any(x > 255 for x in w):
            # 实测有 328 个顶点权重和本来就是 256（源数据自身的舍入余量），并入后可能到 256。
            # 着色器按总权重归一化，钳到 255 的误差 < 0.4%，计数而不 STOP。
            clipped = [k for k in range(N_INFLUENCE) if w[k] > 255]
            for k in clipped:
                w[k] = 255
            stat["clipped_slots"] += len(clipped)
        out[off:off + 8] = bytes(idx)
        out[off + 8:off + 16] = bytes(w)
        stat["vertices_touched"] += 1
        stat["weight_sum_before"].append(before)
        stat["weight_sum_after"].append(sum(w))
        changed_lo = off if changed_lo is None else min(changed_lo, off)
        changed_hi = off + BONE_ELEM_SIZE if changed_hi is None else max(changed_hi, off + BONE_ELEM_SIZE)
    stat["changed_byte_range"] = [changed_lo, changed_hi]
    return bytes(out), stat


def diffs(before, after):
    """返回变化的字节区间列表（用于证明只动了 BoneInfo 区）。"""
    if len(before) != len(after):
        raise ManualReviewRequired("改写后长度变化（%d -> %d）" % (len(before), len(after)))
    spans = []
    start = None
    for i, (a, b) in enumerate(zip(before, after)):
        if a != b:
            if start is None:
                start = i
        elif start is not None:
            spans.append((start, i))
            start = None
    if start is not None:
        spans.append((start, len(before)))
    return spans


def scan_inert_bones(slot_names, used, player_names, mixed=None):
    """只读判定：哪些**加权骨**在 player 侧无人驱动。

    v0.2 判据：
      1. slot 名不在玩家骨名集里 ⇒ 该骨在 player 侧无人驱动（区域刚性冻结）；
      2. 若它的顶点还与玩家骨混合蒙皮（`mixed` 计数，两边权重都 ≥ 阈值）⇒ 交界撕裂 = 可见剪切；
      3. 若整块区域只由它自己驱动（纯 inert）⇒ 只是"冻结"，无撕裂，**不需要动**（头发/耳朵/尾巴）。

    返回 [(slot, name, rec, mixed_count)]，按混合顶点数降序。
    """
    pl = {n.lower() for n in player_names}
    out = []
    for slot, name in enumerate(slot_names):
        r = used.get(slot)
        if not r or name.lower() in pl:
            continue
        out.append((slot, name, r, (mixed or {}).get(slot, 0)))
    out.sort(key=lambda x: (-x[3], -x[2].get("vertices", 0)))
    return out


def scan_mixing(data, geo, slot_names, player_names, threshold=0.2):
    """统计每个槽位"与玩家骨混合蒙皮"的顶点数（判据 2 的分母）。

    混合 = 该顶点上，inert 骨与玩家骨的最大权重都 ≥ threshold。
    """
    base, nv = geo["bone_info_base"], geo["vertex_count"]
    pl = {n.lower() for n in player_names}
    inert_slot = [i for i, n in enumerate(slot_names) if n.lower() not in pl]
    inert_set = set(inert_slot)
    mixed = {i: 0 for i in inert_slot}
    for v in range(nv):
        off = base + v * BONE_ELEM_SIZE
        idx = data[off:off + 8]
        w = data[off + 8:off + 16]
        best_pl = 0.0
        hit = []
        for k in range(N_INFLUENCE):
            if not w[k]:
                continue
            if idx[k] in inert_set:
                hit.append((idx[k], w[k] / 255.0))
            else:
                best_pl = max(best_pl, w[k] / 255.0)
        if best_pl < threshold:
            continue
        for s, wi in hit:
            if wi >= threshold:
                mixed[s] += 1
    return mixed


def main(argv=None):
    ap = argparse.ArgumentParser(description="MESH 顶点权重判定（槽位表语义）/ 等长改写")
    ap.add_argument("mesh")
    ap.add_argument("--map", action="append", default=[],
                    help="{子骨槽位名}:{父骨槽位名}（大小写不敏感），可重复")
    ap.add_argument("--scan", action="store_true",
                    help="只读：列出 player 侧无人驱动的加权骨 + 与玩家骨混合蒙皮的规模")
    ap.add_argument("--player-names", default="base/player-bone-names.json",
                    help="玩家骨名集 JSON（list[str]）；默认 base/player-bone-names.json")
    ap.add_argument("--region-below-y", type=float,
                    help="定点手术：只对绑定坐标 y 小于该值的顶点生效")
    ap.add_argument("--region-abs-x-below", type=float,
                    help="定点手术：只对 |x| 小于该值的顶点生效（限定在颈柱/中轴附近）")
    ap.add_argument("--region-radius-below", type=float,
                    help="定点手术：只对「到 Neck_00→Head_00 轴距离 < 该值」的顶点生效"
                         "（把改动限制在真正的颈管内，排除肩/锁骨/领口壳）")
    ap.add_argument("--ramp-y", metavar="FULL:ZERO",
                    help="渐变转移：y<=FULL 转 100%%，y>=ZERO 转 0%%，中间线性；"
                         "用于避免在平滑表面上留下硬接缝")
    ap.add_argument("--body-only", action="store_true",
                    help="只对「最大权重落在玩家骨名集内」的顶点生效（排除头发/耳朵等装饰件主导的顶点）")
    ap.add_argument("--only-if-dominant", action="store_true",
                    help="定点手术：只在该顶点最大权重落在被并骨上时生效")
    ap.add_argument("--out", help="输出 mesh 路径（--scan 时可省略）")
    ap.add_argument("--report", help="写入 JSON 报告")
    ap.add_argument("--allow-version", action="append", default=[],
                    help="额外允许的 MESH 版本，如 0x014160A8（研究用途）")
    args = ap.parse_args(argv)

    src = Path(args.mesh)
    data = src.read_bytes()
    allowed = (SUPPORTED_MESH_VERSION,) + tuple(int(v, 0) for v in args.allow_version)
    geo = locate_geometry(data, allowed)
    sk = parse_mesh_skeleton(data, source=str(src), allowed_versions=allowed)

    # v0.2：骨身份必须走蒙皮槽位表，不能拿关节数组当索引（否则判错骨、改坏部件）
    slot_joints = read_skin_slots(data, sk)
    slot_names = [sk.joint_names[j] for j in slot_joints]
    used = scan_influences(data, geo)
    unknown = sorted({i for i in used if i >= len(slot_names)})
    if unknown:
        raise SystemExit("STOP：BoneInfo 出现超出槽位表的槽位下标 %s" % unknown)

    _pn = json.loads(Path(args.player_names).read_text(encoding="utf-8-sig"))
    player_names = _pn["names"] if isinstance(_pn, dict) else list(_pn)
    if not player_names:
        raise SystemExit("STOP：玩家骨名集为空（%s）" % args.player_names)
    mixed = scan_mixing(data, geo, slot_names, player_names)

    if args.scan:
        inert = scan_inert_bones(slot_names, used, player_names, mixed)
        print("%s：顶点 %d；关节 %d；蒙皮槽位 %d；玩家骨名集 %d"
              % (src.name, geo["vertex_count"], sk.joint_count, len(slot_names), len(player_names)))
        print("player 侧无人驱动的加权骨 %d 根（按「与玩家骨混合」的顶点数排序）：" % len(inert))
        print("   %-18s %-5s %-7s %-9s %-9s %s" % ("槽位骨名", "槽位", "顶点", "权重和", "最大权重", "混合顶点"))
        for slot, name, r, mx in inert:
            print("   %-18s #%-4d %-7d %-9.2f %-9.3f %d"
                  % (name, slot, r["vertices"], r["weight_sum"], r["weight_max"], mx))
        pure = [n for _, n, _, mx in inert if mx == 0]
        print("   其中纯冻结（无混合 ⇒ 无撕裂，不应处理）：%s" % (", ".join(pure) if pure else "无"))
        if args.report:
            p = Path(args.report)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({
                "mesh": str(src), "vertex_count": geo["vertex_count"],
                "joint_count": sk.joint_count, "slot_count": len(slot_names),
                "player_names": len(player_names),
                "inert": [{"slot": s, "bone": n, "influences": r, "mixed_vertices": mx}
                          for s, n, r, mx in inert],
            }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        return 0

    if not args.map:
        raise SystemExit("STOP：需要 --map（或先用 --scan 看候选）")
    if not args.out:
        raise SystemExit("STOP：改写需要 --out")

    by_slot = {}
    for s, n in enumerate(slot_names):
        by_slot.setdefault(n.lower(), []).append(s)
    mapping = {}
    for spec in args.map:
        child, _, parent = spec.partition(":")
        cs, ps = by_slot.get(child.lower()), by_slot.get(parent.lower())
        if not cs:
            raise SystemExit("STOP：槽位表里没有骨 %s（--scan 可看全部槽位名）" % child)
        if not ps:
            raise SystemExit("STOP：槽位表里没有父骨 %s" % parent)
        if len(cs) > 1:
            raise SystemExit("STOP：槽位名 %s 歧义 %s" % (child, cs))
        if ps[0] == cs[0]:
            raise SystemExit("STOP：%s 的父骨不能是自身" % child)
        mapping[cs[0]] = ps[0]
    print("槽位映射：%s" % ", ".join("#%d(%s) -> #%d(%s)"
          % (c, slot_names[c], p, slot_names[p]) for c, p in sorted(mapping.items())))

    allow = None
    frac = None
    need_pos = (args.region_below_y is not None or args.region_abs_x_below is not None
                or args.ramp_y or args.body_only or args.only_if_dominant
                or args.region_radius_below is not None)
    if need_pos:
        pos = read_positions(data, geo)
        axis = None
        if args.region_radius_below is not None:
            import head_neck_axis as _hna
            wm = _hna.world_matrices(sk)
            ni = {j.name.lower(): j.index for j in sk.joints}.get("neck_00")
            hi = {j.name.lower(): j.index for j in sk.joints}.get("head_00")
            if ni is None or hi is None:
                raise SystemExit("STOP：骨架里没有 Neck_00 / Head_00，无法用半径限定")
            axis = (_hna._world_pos(wm[ni]), _hna._world_pos(wm[hi]))
        cut, axcut = args.region_below_y, args.region_abs_x_below
        ramp = None
        if args.ramp_y:
            f, _, z = args.ramp_y.partition(":")
            y_full, y_zero = float(f), float(z)
            if y_zero <= y_full:
                raise SystemExit("STOP：--ramp-y 需要 FULL < ZERO（y 越大转移越少）")
            ramp = (y_full, y_zero)
        pl = {n.lower() for n in player_names}

        def allow(v):
            x, y, _z = pos[v]
            if axis is not None:
                a, b = axis
                vx, vy, vz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
                wx, wy, wz = pos[v][0] - a[0], pos[v][1] - a[1], pos[v][2] - a[2]
                vv = vx * vx + vy * vy + vz * vz
                t_ = 0.0 if vv <= 0 else max(0.0, min(1.0, (wx * vx + wy * vy + wz * vz) / vv))
                dx = pos[v][0] - (a[0] + t_ * vx)
                dy = pos[v][1] - (a[1] + t_ * vy)
                dz = pos[v][2] - (a[2] + t_ * vz)
                if (dx * dx + dy * dy + dz * dz) ** 0.5 >= args.region_radius_below:
                    return False
            if cut is not None and y >= cut:
                return False
            if axcut is not None and abs(x) >= axcut:
                return False
            if args.only_if_dominant:
                off = geo["bone_info_base"] + v * BONE_ELEM_SIZE
                idx = data[off:off + 8]
                w = data[off + 8:off + 16]
                best = max(range(N_INFLUENCE), key=lambda k: (w[k] if w[k] else -1))
                if best < 0 or idx[best] not in mapping:
                    return False
            if args.body_only:
                off = geo["bone_info_base"] + v * BONE_ELEM_SIZE
                idx = data[off:off + 8]
                w = data[off + 8:off + 16]
                best = max(range(N_INFLUENCE), key=lambda k: (w[k] if w[k] else -1))
                if best < 0 or slot_names[idx[best]].lower() not in pl:
                    return False
            return True

        def frac(v):
            if ramp is None:
                return 1.0
            y_full, y_zero = ramp
            y = pos[v][1]
            if y <= y_full:
                return 1.0
            if y >= y_zero:
                return 0.0
            return (y_zero - y) / (y_zero - y_full)

        print("区域限定：%s%s%s%s%s" % (
            ("到颈轴半径 < %.4f" % args.region_radius_below) if axis is not None else "",
            ("；y < %.4f" % cut) if cut is not None else "",
            ("；|x| < %.4f" % axcut) if axcut is not None else "",
            ("；渐变 y %.4f→%.4f（100%%→0%%）" % ramp) if ramp else "",
            "；仅玩家骨主导的顶点" if args.body_only else ""))

    print("顶点 %d；受映射影响的骨：" % geo["vertex_count"])
    for c in sorted(mapping):
        r = used.get(c)
        print("   #%-3d %-16s %s" % (c, slot_names[c],
              "顶点 %-5d 权重和 %.2f 最大 %.3f" % (r["vertices"], r["weight_sum"], r["weight_max"])
              if r else "未驱动任何顶点"))

    out_data, stat = rebind(data, geo, mapping, allow=allow, frac=frac)
    spans = diffs(data, out_data)
    lo, hi = geo["bone_info_base"], geo["bone_info_base"] + geo["vertex_count"] * BONE_ELEM_SIZE
    outside = [(a, b) for a, b in spans if a < lo or b > hi]
    if outside:
        raise SystemExit("STOP：改动越出 BoneInfo 区 %s" % outside)
    if any(b > a for a, b in zip(stat["weight_sum_before"], stat["weight_sum_after"])):
        raise SystemExit("STOP：并骨后出现权重和增加（不守恒）；只允许因钳制而持平或减少")

    dst = Path(args.out)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(out_data)

    # 写回后重新解析，确认结构未变且映射已生效
    geo2 = locate_geometry(out_data, allowed)
    used2 = scan_influences(out_data, geo2)
    residual = {c: used2.get(c) for c in mapping if used2.get(c)}
    report = {
        "source": str(src), "output": str(dst),
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "output_sha256": hashlib.sha256(out_data).hexdigest(),
        "mesh_version": geo["version"],
        "vertex_count": geo["vertex_count"],
        "joint_count": sk.joint_count,
        "slot_count": len(slot_names),
        "mapping_slots": {str(c): p for c, p in mapping.items()},
        "mapping": {slot_names[c]: slot_names[p] for c, p in mapping.items()},
        "region": {"below_y": args.region_below_y, "only_if_dominant": bool(args.only_if_dominant),
                   "radius_below": args.region_radius_below,
                   "abs_x_below": args.region_abs_x_below, "ramp_y": args.ramp_y,
                   "body_only": bool(args.body_only)},
        "bone_info_range": [lo, hi],
        "changed_spans": spans,
        "changed_bytes": sum(b - a for a, b in spans),
        "geometry_unchanged": {k: geo[k] for k in
                               ("vertex_buffer", "face_index_buffer", "elements",
                                "bone_info_offset_in_vb", "vertex_count")}
                            == {k: geo2[k] for k in
                                ("vertex_buffer", "face_index_buffer", "elements",
                                 "bone_info_offset_in_vb", "vertex_count")},
        "stat": {k: v for k, v in stat.items()
                 if k not in ("weight_sum_before", "weight_sum_after")},
        "residual_children_still_used": {str(k): v for k, v in residual.items()},
    }
    if args.report:
        p = Path(args.report)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8", newline="\n")

    print()
    print("受影响顶点 %d / %d；改动 %d 字节，区间 %s"
          % (stat["vertices_touched"], geo["vertex_count"], report["changed_bytes"],
             ["0x%X..0x%X" % s for s in spans]))
    print("  并入已有父骨槽位 %d；复用空槽 %d；权重单位迁移 %d"
          % (stat["vertices_merged_into_existing"], stat["vertices_reused_slot"],
             stat["moved_weight_units"]))
    print("  几何段未变：%s；钳制槽位 %d（源权重和 256 的顶点并入后的舍入余量）"
          % (report["geometry_unchanged"], stat["clipped_slots"]))
    print("  残留（应只剩权重 0 的名义条目）：%s"
          % (residual if residual else "无"))
    print("输出 %s（%d 字节，原 %d 字节）" % (dst, len(out_data), len(data)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

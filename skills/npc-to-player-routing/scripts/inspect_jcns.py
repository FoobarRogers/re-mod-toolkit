#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RE Engine JCNS（Joint Constraint，`.jcns.21`）只读解析器。

研究分支工具（`TODO_NPC709_FaceRuntime_JCNS_Research.md` §8）。**只读、可重放**，
不修改任何资源。

## 已确认的哈希函数

文件内以 u32 形式出现的骨名引用，可用下列函数复现（已逐项验证 8/8）：

    murmur3_x86_32(name.encode("utf-16-le"), seed=0xFFFFFFFF)

实测对应：`L_Leg_00 -> 0x5f3d6f05`、`R_Leg_00 -> 0x58fec33d`、
`L_plus -> 0xf7f3280e`、`L_plus2 -> 0x199b9b02`、`L_plus3 -> 0x4a1d665a`、
`R_plus -> 0xf3ad5a10`、`R_plus2 -> 0x26c8eb31`、`R_plus3 -> 0x2eb5ad5b`。

## 已确认的文件布局（NPC709 样本）

```text
0x00 u32 version (= 21，对应扩展名 .21)
0x04 char[4] "jcns"
0x10 u64 0x30     0x20 u64 0x40     0x30 u64 0x0f
0x40 u64 0x50     0x50 u64 0xb0     0x60 u64 0x9e0
0x88 u64 0x9e0    0x90 u64 0x950
0xa0 ...  12 条无名字段记录，步长 0x50
0x468 ... 12 条带名字段记录，步长 0x60（名字为 +0x50 起 16 字节 UTF-16LE）
0x8f0 ... 6 个骨名，步长 0x10
0x950 ... 6 × {u64 指针, u32 1, u32 0}
0x9b0 ... 6 × {u32 骨名哈希, u32 参考骨哈希}
```

**未确认**：记录内部的数值字段语义（角度阈值、轴、限位等）未经独立验证，
本工具只报告"哪些字段非零"，不解释其含义，也不据其推断运行时行为。
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

JCNS_MAGIC = b"jcns"
SUPPORTED_JCNS_VERSION = 21

# 记录区（NPC709 样本实测，并经下列不变量校验后才采用）：
#   - 每条带名记录 +0x44 必为 1.0f
#   - 每条带名记录 +0x10 的骨名哈希 == murmur3(记录内 +0x48 的名字)
#   - 12 条无名记录 +0x18 的 u64 指针恰好等于 12 条带名记录的起点
#   - 带名记录区结束位置恰好等于 name array 起点 0x8f0
UNNAMED_ARRAY_OFFSET = 0xA0
UNNAMED_RECORD_SIZE = 0x50
NAMED_ARRAY_OFFSET = 0x470
NAMED_RECORD_SIZE = 0x60
RECORD_COUNT = 12
NAME_FIELD_OFFSET = 0x48
NAME_FIELD_SIZE = 0x10
ONE_FLOAT_OFFSET = 0x44
BONE_NAME_HASH_OFFSET = 0x10       # 带名记录内：本记录的骨名哈希
PARTNER_PTR_OFFSET = 0x18          # 无名记录内：指向对应带名记录起点的 u64
PARTNER_HASH_OFFSET = 0x30         # 无名记录内：关联骨名（L_plus 等）的哈希
NAME_ARRAY_OFFSET = 0x8F0
NAME_ARRAY_STRIDE = 0x10
NAME_ARRAY_COUNT = 6
SLOT_TABLE_OFFSET = 0x950
SLOT_TABLE_STRIDE = 0x10
SLOT_TABLE_COUNT = 6
SLOT_PAIR_OFFSET = 0x9B0           # 由 SLOT_TABLE 的 u64 指针指向


class ManualReviewRequired(Exception):
    pass


def murmur3_x86_32(data: bytes, seed: int = 0) -> int:
    c1, c2 = 0xCC9E2D51, 0x1B873593
    h = seed & 0xFFFFFFFF
    n = len(data)
    i = 0
    while i + 4 <= n:
        k = struct.unpack_from("<I", data, i)[0]
        k = (k * c1) & 0xFFFFFFFF
        k = ((k << 15) | (k >> 17)) & 0xFFFFFFFF
        k = (k * c2) & 0xFFFFFFFF
        h ^= k
        h = ((h << 13) | (h >> 19)) & 0xFFFFFFFF
        h = (h * 5 + 0xE6546B64) & 0xFFFFFFFF
        i += 4
    tail = data[i:]
    k = 0
    if len(tail) >= 3:
        k ^= tail[2] << 16
    if len(tail) >= 2:
        k ^= tail[1] << 8
    if len(tail) >= 1:
        k ^= tail[0]
        k = (k * c1) & 0xFFFFFFFF
        k = ((k << 15) | (k >> 17)) & 0xFFFFFFFF
        k = (k * c2) & 0xFFFFFFFF
        h ^= k
    h ^= n
    h ^= h >> 16
    h = (h * 0x85EBCA6B) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 0xC2B2AE35) & 0xFFFFFFFF
    h ^= h >> 16
    return h


def bone_name_hash(name: str) -> int:
    """JCNS 中骨名引用的哈希（已实测验证 8/8）。"""
    return murmur3_x86_32(name.encode("utf-16-le"), 0xFFFFFFFF)


def build_hash_index(names):
    return {bone_name_hash(n): n for n in names}


def _read_u16_string(data, offset, size):
    raw = data[offset:offset + size]
    text = raw.decode("utf-16-le", errors="replace")
    return text.split("\x00", 1)[0]


def parse_jcns(data, source="<bytes>", known_joints=()):
    if data[4:8] != JCNS_MAGIC:
        raise ManualReviewRequired("%s: jcns magic 不匹配（%r）" % (source, data[4:8]))
    version = struct.unpack_from("<I", data, 0)[0]
    if version != SUPPORTED_JCNS_VERSION:
        raise ManualReviewRequired(
            "%s: jcns version %d 未经验证（只支持 %d）" % (source, version, SUPPORTED_JCNS_VERSION)
        )
    size = len(data)
    needed = max(
        UNNAMED_ARRAY_OFFSET + UNNAMED_RECORD_SIZE * RECORD_COUNT,
        NAMED_ARRAY_OFFSET + NAMED_RECORD_SIZE * RECORD_COUNT,
        SLOT_PAIR_OFFSET + 8 * SLOT_TABLE_COUNT,
    )
    if size < needed:
        raise ManualReviewRequired("%s: 文件 %d 字节，小于已确认布局所需 %d" % (source, size, needed))

    index = build_hash_index(known_joints)

    unnamed = []
    for k in range(RECORD_COUNT):
        o = UNNAMED_ARRAY_OFFSET + UNNAMED_RECORD_SIZE * k
        ptr, = struct.unpack_from("<Q", data, o + PARTNER_PTR_OFFSET)
        partner_hash, = struct.unpack_from("<I", data, o + PARTNER_HASH_OFFSET)
        expected_ptr = NAMED_ARRAY_OFFSET + NAMED_RECORD_SIZE * k
        unnamed.append({
            "index": k,
            "offset": o,
            "partner_ptr": ptr,
            "partner_ptr_expected": expected_ptr,
            "partner_ptr_matches": ptr == expected_ptr,
            "partner_hash": "%08x" % partner_hash,
            "partner_name": index.get(partner_hash),
        })

    named = []
    for k in range(RECORD_COUNT):
        o = NAMED_ARRAY_OFFSET + NAMED_RECORD_SIZE * k
        name = _read_u16_string(data, o + NAME_FIELD_OFFSET, NAME_FIELD_SIZE)
        one, = struct.unpack_from("<f", data, o + ONE_FLOAT_OFFSET)
        bone_hash, = struct.unpack_from("<I", data, o + BONE_NAME_HASH_OFFSET)
        params = []
        for rel in range(0x18, ONE_FLOAT_OFFSET, 4):
            v, = struct.unpack_from("<f", data, o + rel)
            if v != 0.0 and v == v and abs(v) < 1e30:
                params.append({"rel_offset": "0x%02x" % rel, "value": v})
        if one != 1.0:
            raise ManualReviewRequired(
                "%s: 记录 %d 的 +0x%02x 不是 1.0f（%.9g），布局假设不成立"
                % (source, k, ONE_FLOAT_OFFSET, one)
            )
        named.append({
            "index": k,
            "offset": o,
            "name": name,
            "name_hash_computed": "%08x" % bone_name_hash(name),
            "name_hash_in_file": "%08x" % bone_hash,
            "name_hash_matches": bone_name_hash(name) == bone_hash,
            "nonzero_param_candidates": params,
        })

    # 名字数组 + slot 表
    extra_names = [
        _read_u16_string(data, NAME_ARRAY_OFFSET + NAME_ARRAY_STRIDE * k, NAME_ARRAY_STRIDE)
        for k in range(NAME_ARRAY_COUNT)
    ]
    slots = []
    for k in range(SLOT_TABLE_COUNT):
        o = SLOT_TABLE_OFFSET + SLOT_TABLE_STRIDE * k
        ptr, count = struct.unpack_from("<QI", data, o)
        a, b = struct.unpack_from("<2I", data, ptr) if ptr + 8 <= size else (0, 0)
        slots.append({
            "index": k,
            "table_offset": o,
            "slot_ptr": ptr,
            "slot_count": count,
            "name_from_name_array": extra_names[k] if k < len(extra_names) else None,
            "hash_a": "%08x" % a,
            "hash_b": "%08x" % b,
            "name_a": index.get(a),
            "name_b": index.get(b),
        })

    # 全文件哈希扫描：把每个 4 字节位置当作候选哈希，尝试解析为已知骨名
    resolved = []
    for off in range(0, size - 3):
        v, = struct.unpack_from("<I", data, off)
        if v in index:
            resolved.append({"offset": off, "hash": "%08x" % v, "name": index[v]})

    named_names = sorted({r["name"] for r in named if r["name"]})
    extra_named = sorted({n for n in extra_names if n})
    all_referenced = sorted({
        r["name_b"] for r in slots if r["name_b"]
    } | {r["name_a"] for r in slots if r["name_a"]} | set(named_names))
    unresolved_partner_hashes = sorted({
        r["partner_hash"] for r in unnamed
        if r["partner_name"] is None and r["partner_hash"] != "00000000"
    })
    unresolved_names = [n for n in extra_names if n and bone_name_hash(n) not in index]

    return {
        "source": source,
        "file_size": size,
        "version": version,
        "layout_assumed": {
            "unnamed_array_offset": UNNAMED_ARRAY_OFFSET,
            "unnamed_record_size": UNNAMED_RECORD_SIZE,
            "named_array_offset": NAMED_ARRAY_OFFSET,
            "named_record_size": NAMED_RECORD_SIZE,
            "record_count": RECORD_COUNT,
            "one_float_offset": ONE_FLOAT_OFFSET,
            "note": "偏移来自 NPC709 单样本实测 + 1.0f 不变量校验；未经第二个样本复现。",
        },
        "known_joint_count": len(known_joints),
        "unnamed_records": unnamed,
        "named_records": named,
        "name_array": extra_names,
        "slot_table": slots,
        "all_resolvable_hashes_in_file": resolved,
        "distinct_bones_referenced": all_referenced,
        "head_neck_referenced": sorted(
            b for b in all_referenced
            if any(t in b.lower() for t in ("neck", "head", "spine", "jaw", "face", "lookat", "cog", "waist"))
        ),
        "name_hash_selfcheck_all_pass": all(r["name_hash_matches"] for r in named),
        "partner_ptr_selfcheck_all_pass": all(r["partner_ptr_matches"] for r in unnamed),
        "unresolved_partner_hashes": unresolved_partner_hashes,
        "names_not_in_joint_list": unresolved_names,
    }


def render_txt(rep):
    L = []
    L.append("JCNS 解析报告 —— %s" % rep["source"])
    L.append("size=%d  version=%d" % (rep["file_size"], rep["version"]))
    L.append("已知骨名表规模 = %d" % rep["known_joint_count"])
    L.append("骨名自校验（记录内 name 与 hash 一致）：%s" % rep["name_hash_selfcheck_all_pass"])
    L.append("")
    L.append("带名记录（%d）：" % len(rep["named_records"]))
    for r in rep["named_records"]:
        params = " ".join("%s=%.6g" % (p["rel_offset"], p["value"]) for p in r["nonzero_param_candidates"])
        L.append("  N%02d @0x%03x  %-10s hash=%s match=%s  %s" % (
            r["index"], r["offset"], r["name"], r["name_hash_in_file"], r["name_hash_matches"], params))
    L.append("")
    L.append("无名记录 ↔ 带名记录的配对指针（%d）：" % len(rep["unnamed_records"]))
    for r in rep["unnamed_records"]:
        L.append("  U%02d @0x%03x  partner_ptr=0x%x (expected 0x%x, %s)  partner_hash=%s  partner_name=%s" % (
            r["index"], r["offset"], r["partner_ptr"], r["partner_ptr_expected"],
            "ok" if r["partner_ptr_matches"] else "MISMATCH",
            r["partner_hash"], r["partner_name"]))
    L.append("")
    L.append("配对指针自校验：%s" % rep["partner_ptr_selfcheck_all_pass"])
    L.append("未解析的 partner 哈希：%s" % (rep["unresolved_partner_hashes"] or "(none)"))
    L.append("name array 中不在关节表内的名字：%s" % (rep["names_not_in_joint_list"] or "(none)"))
    L.append("")
    L.append("name array（%d）：%s" % (len(rep["name_array"]), rep["name_array"]))
    L.append("")
    L.append("slot table（%d）：" % len(rep["slot_table"]))
    for s in rep["slot_table"]:
        L.append("  S%d name=%-10s hash_a=%s(%s)  hash_b=%s(%s)" % (
            s["index"], s["name_from_name_array"], s["hash_a"], s["name_a"], s["hash_b"], s["name_b"]))
    L.append("")
    L.append("全文件可解析骨名哈希命中（%d）：" % len(rep["all_resolvable_hashes_in_file"]))
    for h in rep["all_resolvable_hashes_in_file"]:
        L.append("  @0x%03x  %s  %s" % (h["offset"], h["hash"], h["name"]))
    L.append("")
    L.append("被引用的不同骨名（%d）：%s" % (len(rep["distinct_bones_referenced"]), rep["distinct_bones_referenced"]))
    L.append("其中头/颈/脊柱/面相关：%s" % (rep["head_neck_referenced"] or "(none)"))
    L.append("")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description="解析 RE Engine .jcns（只读研究工具）")
    ap.add_argument("jcns")
    ap.add_argument("--joints-from", action="append", default=[],
                    help="从该 mesh 取关节名作为哈希解析表（可重复）")
    ap.add_argument("--joints-json", action="append", default=[],
                    help="从该 JSON（含 joint_names 数组）取关节名")
    ap.add_argument("--json", help="输出 JSON 报告路径")
    ap.add_argument("--txt", help="输出文本报告路径")
    args = ap.parse_args(argv)

    joints = []
    versions = [0x014111C0, 0x0141D2B8]
    from mesh_skeleton import load_mesh_skeleton

    for m in args.joints_from:
        joints.extend(load_mesh_skeleton(m, allowed_versions=versions).joint_names)
    for j in args.joints_json:
        doc = json.loads(Path(j).read_text(encoding="utf-8"))
        joints.extend(doc.get("joint_names", []))
    joints = sorted(set(joints))

    try:
        rep = parse_jcns(Path(args.jcns).read_bytes(), source=str(args.jcns), known_joints=joints)
    except ManualReviewRequired as exc:
        print("MANUAL_REVIEW_REQUIRED")
        print("  " + str(exc))
        return 2

    if args.json:
        p = Path(args.json)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(rep, indent=2, ensure_ascii=False) + "\n")
    if args.txt:
        p = Path(args.txt)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(render_txt(rep))

    print("JCNS 解析 PASS  version=%d  size=%d" % (rep["version"], rep["file_size"]))
    print("带名记录 %d，无名记录 %d，slot %d" % (
        len(rep["named_records"]), len(rep["unnamed_records"]), len(rep["slot_table"])))
    print("被引用骨名：%s" % ", ".join(rep["distinct_bones_referenced"]))
    print("头颈相关引用：%s" % (", ".join(rep["head_neck_referenced"]) or "(none)"))
    print("name/hash 自校验：%s" % rep["name_hash_selfcheck_all_pass"])
    return 0


if __name__ == "__main__":
    sys.exit(main())

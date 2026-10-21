#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RE Engine PFB（`.pfb.17`）源资源引用图 —— 研究分支只读工具。

目的（`TODO_NPC709_FaceRuntime_JCNS_Research.md` §5）：把源 NPC 的 PFB 当作
**Source Blueprint**，提取它引用了哪些资源，而不是把它当"NPC 入口文件"。

## 已确认（NPC709 `nid709.pfb.17` 实测 + 结构自洽）

```text
0x00 char[4]  "PFB\\0"
0x04 u32      version = 7
0x08 u32      path_table_count   (20)
0x0c u32      未确认
0x10 u32      typed_ref_count    (11)
0x14 u32      0
0x18 u64      未确认 (0x8c)
0x20 u64      path_table_offset        -> path_table_count 个 u64（字符串偏移）
0x28 u64      typed_ref_table_offset   -> typed_ref_count 个 {u32 class_hash, u32 0, u64 str_off}
0x30 u64      第一个字符串块结束位置
0x38 u32      0
0x3c u32      0xFFFFFFFF
0x40..       未确认（疑似对象/组件描述表）
```

**未确认**：0x0c、0x18、0x40 起区域；对象-组件父子关系；局部 transform。
本工具不猜这些字段，只报告"哪些证据成立、哪些字段仍未定位"。

## 分类原则

按 TODO §5 的核心原则：**不得根据文件名/目录名/"看起来像"直接判定可丢弃**。
因此本工具只做两件事：

1. `roles_by_reference_structure` —— 由**引用结构**（例如"与玩家脸部运行时资源
   同组出现"）得出的分组，属于结构性证据；
2. `roles_by_path_pattern` —— 由路径/扩展名得出的分组，**明确标注为路径模式推导**，
   仅用于组织报告，不作为"可安全丢弃"的依据。

可丢弃性一律输出 `UNDECIDED`，由后续实验决定。
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from pathlib import Path

PFB_MAGIC = b"PFB\x00"
SUPPORTED_PFB_VERSION = 7

_U16_RUN = re.compile(rb"(?:[\x20-\x7e]\x00){3,}")

# 猎人型 NPC / 流浪猎人系：玩家侧脸部运行时链路。
# 依据：NPC709 的 PFB 把这些资源与 `nid709_face` 放在同一组，
# 且路径全部位于 `player/`（玩家 hunter 框架）下。
HUNTER_FACE_RUNTIME = {
    "player/mod/face/pl_face000.mdf2": "FACE_MATERIAL_DEFAULT",
    "player/face_mot/PlayerFaceJointMap.jmap": "FACE_JOINT_MAP",
    "player/face_mot/PlayerFaceJointLOD.jointlodgroup": "FACE_JOINT_LOD",
    "player/face_data/PlayerUserDataCharaMake.user": "FACE_CHARAMAKE_DATA",
}

# 路径模式 → 角色分组（仅用于组织报告，不用于判定可丢弃性）
PATH_PATTERN_ROLES = (
    (r"^player/mod/face/pl_face\d+\.mesh$", "FACE_GEOMETRY_PLAYER_SLOT"),
    (r"\.jcns$", "JOINT_CONSTRAINT"),
    (r"\.chain$", "PHYSICS"),
    (r"\.mdf2$", "MATERIAL"),
    (r"\.tex$", "TEXTURE"),
    (r"\.mesh$", "GEOMETRY"),
    (r"\.wcc$", "AUDIO_CONTAINER"),
    (r"\.msg$", "TEXT_MESSAGE"),
    (r"\.gui$", "UI"),
    (r"\.fsmv2$|\.motfsm2$", "NPC_BEHAVIOR"),
    (r"\.motbank$", "ANIMATION_BANK"),
    (r"_jointmap\.jmap$", "JOINT_MAP"),
    (r"\.jointlodgroup$", "JOINT_LOD_GROUP"),
    (r"\.iklookat2$", "LOOKAT"),
    (r"\.rcol$", "COLLISION"),
    (r"/item/.*\.mesh$", "PROP"),
    (r"_HeadMesPos\.user$", "HEAD_MESH_POSITION_PARAM"),
    (r"_facialparam\.user$", "FACIAL_PARAM"),
    (r"_faceMaterial\.user$", "FACE_MATERIAL_PARAM"),
    (r"\.user$", "USER_DATA"),
)


class ManualReviewRequired(Exception):
    pass


def _strings(data):
    out = []
    for m in _U16_RUN.finditer(data):
        out.append({
            "offset": m.start(),
            "text": m.group().decode("utf-16-le"),
            "byte_length": m.end() - m.start(),
        })
    return out


def _is_path(text):
    return "/" in text or "." in text


def parse_pfb(data, source="<bytes>", allowed_versions=None):
    """解析 PFB。

    `allowed_versions` 默认 `None` —— 只接受生产已验证的 `SUPPORTED_PFB_VERSION`。
    研究分支可显式传入额外版本做**只读结构探测**（例如 NPC4 系列的 v6），
    但不得用放开后的结果直接改写生产资源；生产调用点一律不传该参数。
    """
    if data[:4] != PFB_MAGIC:
        raise ManualReviewRequired("%s: PFB magic 不匹配（%r）" % (source, data[:4]))
    accepted = (SUPPORTED_PFB_VERSION,) if allowed_versions is None else tuple(allowed_versions)
    version = struct.unpack_from("<I", data, 4)[0]
    if version not in accepted:
        raise ManualReviewRequired(
            "%s: PFB version %d 未经验证（只支持 %s）"
            % (source, version, ", ".join(str(v) for v in accepted))
        )
    size = len(data)

    path_count, unk_0c, ref_count, _ = struct.unpack_from("<4I", data, 0x08)
    unk_18, = struct.unpack_from("<Q", data, 0x18)
    path_table_off, ref_table_off, strings_end = struct.unpack_from("<3Q", data, 0x20)

    if not (0x40 <= path_table_off < size and 0x40 <= ref_table_off <= size):
        raise ManualReviewRequired("%s: 表偏移越界（0x%x / 0x%x）" % (source, path_table_off, ref_table_off))
    if path_table_off + 8 * path_count > size or ref_table_off + 16 * ref_count > size:
        raise ManualReviewRequired("%s: 表规模超出文件" % source)

    strings = _strings(data)
    by_offset = {s["offset"]: s for s in strings}

    def text_at(off):
        s = by_offset.get(off)
        if s is None:
            raise ManualReviewRequired("%s: 偏移 0x%x 不是已识别的 UTF-16 字符串起点" % (source, off))
        return s["text"]

    path_table = []
    for k in range(path_count):
        off, = struct.unpack_from("<Q", data, path_table_off + 8 * k)
        path_table.append({"index": k, "entry_offset": path_table_off + 8 * k,
                           "string_offset": off, "path": text_at(off)})

    typed_refs = []
    for k in range(ref_count):
        o = ref_table_off + 16 * k
        cls, pad, off = struct.unpack_from("<IIQ", data, o)
        typed_refs.append({
            "index": k, "entry_offset": o,
            "class_hash": "%08x" % cls, "reserved": pad,
            "string_offset": off, "path": text_at(off),
        })

    # 字符串块划分：以第一个块结束位置为界
    block1 = [s for s in strings if s["offset"] < strings_end]
    later = [s for s in strings if s["offset"] >= strings_end]

    # 引用可达性：整个文件里是否存在指向该字符串起点的偏移（u32，任意字节对齐）
    pointing = {}
    for off in range(0, size - 3):
        v, = struct.unpack_from("<I", data, off)
        if v:
            pointing.setdefault(v, []).append(off)

    # 第二个 section 采用"相对 strings_end 寻址"：绝对偏移扫描找不到它。
    # 这里显式把相对寻址也纳入可达性判定。
    def refs_of(string_offset):
        absolute = ["0x%x" % x for x in pointing.get(string_offset, [])]
        rel = string_offset - strings_end
        relative = ["0x%x(+0x%x)" % (x, strings_end) for x in pointing.get(rel, [])] if rel > 0 else []
        return absolute, relative

    # section 2 的第二张引用表：16 字节条目
    # {u32 class_hash, u32 rel_offset, u32 0, u32 object_index}
    # 判定条件：class_hash 出现在第一张 typed_ref 表里，且 strings_end + rel_offset 命中一个字符串。
    known_hashes = {int(e["class_hash"], 16) for e in typed_refs}
    str_offsets = set(by_offset)
    section2_table = []
    for off in range(0x40, size - 16, 4):
        cls, rel, zero, idx = struct.unpack_from("<4I", data, off)
        if cls not in known_hashes or zero != 0:
            continue
        if strings_end + rel not in str_offsets:
            continue
        section2_table.append({
            "entry_offset": off,
            "class_hash": "%08x" % cls,
            "rel_offset": rel,
            "absolute_string_offset": strings_end + rel,
            "path": by_offset[strings_end + rel]["text"],
            "object_index_field": idx,
            # 最后一条条目的 +12 字段会与紧随其后的字符串重叠，此时不可信
            "object_index_field_reliable": idx < 4096,
        })
    # 去掉互相重叠的误命中（同一 class_hash 只保留一个条目）
    dedup = {}
    for e in section2_table:
        dedup.setdefault((e["class_hash"], e["absolute_string_offset"]), e)
    section2_table = [dedup[k] for k in sorted(dedup, key=lambda k: dedup[k]["entry_offset"])]

    later_refs = []
    for s in later:
        absolute, relative = refs_of(s["offset"])
        later_refs.append({
            "offset": s["offset"], "text": s["text"],
            "is_path": _is_path(s["text"]),
            "referenced_absolute": absolute,
            "referenced_relative_to_strings_end": relative,
            "referenced": bool(absolute or relative),
        })

    # 分组：块 2 中"资源路径"按其前置的游戏对象名归组（相邻性推导，明确标注）
    game_objects = [s for s in later if not _is_path(s["text"])]
    role_assignment = []
    for entry in path_table + typed_refs:
        p = entry["path"]
        role = None
        for pattern, name in PATH_PATTERN_ROLES:
            if re.search(pattern, p):
                role = name
                break
        role_assignment.append({
            "path": p,
            "string_offset": entry["string_offset"],
            "role_by_path_pattern": role or "UNCLASSIFIED",
            "hunter_face_runtime": HUNTER_FACE_RUNTIME.get(p),
            "discardability": "UNDECIDED",
        })

    return {
        "source": source,
        "file_size": size,
        "version": version,
        "header": {
            "path_table_count": path_count,
            "unresolved_u32_0x0c": unk_0c,
            "typed_ref_count": ref_count,
            "unresolved_u64_0x18": unk_18,
            "path_table_offset": path_table_off,
            "typed_ref_table_offset": ref_table_off,
            "first_string_block_end": strings_end,
        },
        "path_table": path_table,
        "typed_refs": typed_refs,
        "section2_ref_table": section2_table,
        "addressing": {
            "note": (
                "第二 section 的字符串以 `strings_end` 为基址相对寻址，"
                "因此对整个文件做绝对偏移扫描找不到它们。"
            ),
            "section2_base": strings_end,
        },
        "string_blocks": {
            "first_block_count": len(block1),
            "later_block_count": len(later),
            "later_block_range": [min((s["offset"] for s in later), default=None),
                                  max((s["offset"] for s in later), default=None)],
        },
        "game_object_name_candidates": [
            {"offset": s["offset"], "name": s["text"],
             "referenced_absolute": refs_of(s["offset"])[0],
             "referenced_relative_to_strings_end": refs_of(s["offset"])[1]}
            for s in game_objects
        ],
        "later_block_strings": later_refs,
        "role_assignment": role_assignment,
        "hunter_face_runtime_present": sorted(
            p for p in (e["path"] for e in path_table + typed_refs) if p in HUNTER_FACE_RUNTIME
        ),
        "known_unknowns": [
            "header 0x0c / 0x18 语义未定位",
            "0x40 起区域未解析（疑似对象/组件描述表）",
            "section2 表中 object_index_field 的语义未确认，不能据此断言父子关系",
            "GameObject 与组件资源的父子关系未能从结构上确认",
            "局部 transform 未定位",
        ],
        "classification_caveat": (
            "role_by_path_pattern 由路径/扩展名推导，仅用于组织报告；"
            "按 TODO §5 核心原则，不得据此判定资源可丢弃。discardability 一律 UNDECIDED。"
        ),
    }


def render_md(rep):
    L = []
    L.append("# Source Resource Graph —— %s" % rep["source"])
    L.append("")
    L.append("PFB version %d，文件 %d 字节。" % (rep["version"], rep["file_size"]))
    L.append("")
    h = rep["header"]
    L.append("```text")
    L.append("path_table_count        = %d" % h["path_table_count"])
    L.append("typed_ref_count         = %d" % h["typed_ref_count"])
    L.append("path_table_offset       = 0x%x" % h["path_table_offset"])
    L.append("typed_ref_table_offset  = 0x%x" % h["typed_ref_table_offset"])
    L.append("first_string_block_end  = 0x%x" % h["first_string_block_end"])
    L.append("unresolved u32 @0x0c    = %d" % h["unresolved_u32_0x0c"])
    L.append("unresolved u64 @0x18    = 0x%x" % h["unresolved_u64_0x18"])
    L.append("```")
    L.append("")
    L.append("## 引用表 A —— path_table（%d）" % len(rep["path_table"]))
    L.append("")
    L.append("| # | 字符串偏移 | 资源路径 |")
    L.append("| --- | --- | --- |")
    for e in rep["path_table"]:
        L.append("| %d | 0x%x | `%s` |" % (e["index"], e["string_offset"], e["path"]))
    L.append("")
    L.append("## 引用表 B —— typed_refs（%d，每条含 u32 class hash）" % len(rep["typed_refs"]))
    L.append("")
    L.append("| # | class hash | 字符串偏移 | 资源路径 |")
    L.append("| --- | --- | --- | --- |")
    for e in rep["typed_refs"]:
        L.append("| %d | `%s` | 0x%x | `%s` |" % (e["index"], e["class_hash"], e["string_offset"], e["path"]))
    L.append("")
    L.append("## 引用表 C —— section2_ref_table（%d，相对 `strings_end`=0x%x 寻址）" % (
        len(rep["section2_ref_table"]), rep["header"]["first_string_block_end"]))
    L.append("")
    L.append("| 条目偏移 | class hash | rel_offset | 绝对字符串偏移 | 资源路径 | object_index 字段 |")
    L.append("| --- | --- | --- | --- | --- | --- |")
    for e in rep["section2_ref_table"]:
        L.append("| 0x%x | `%s` | %d | 0x%x | `%s` | %d%s |" % (
            e["entry_offset"], e["class_hash"], e["rel_offset"],
            e["absolute_string_offset"], e["path"], e["object_index_field"],
            "" if e["object_index_field_reliable"] else "（与后续字符串重叠，不可信）"))
    L.append("")
    L.append("## 猎人型 NPC / 流浪猎人系：玩家脸部运行时引用")
    L.append("")
    if rep["hunter_face_runtime_present"]:
        L.append("| 资源 | 角色（结构性） |")
        L.append("| --- | --- |")
        for p in rep["hunter_face_runtime_present"]:
            L.append("| `%s` | %s |" % (p, HUNTER_FACE_RUNTIME[p]))
    else:
        L.append("(none)")
    L.append("")
    L.append("## 角色分组（由路径模式推导，不用于判定可丢弃性）")
    L.append("")
    L.append("| 资源 | 路径模式角色 | 猎人脸部运行时 | 可丢弃性 |")
    L.append("| --- | --- | --- | --- |")
    for e in rep["role_assignment"]:
        L.append("| `%s` | %s | %s | %s |" % (
            e["path"], e["role_by_path_pattern"], e["hunter_face_runtime"] or "-", e["discardability"]))
    L.append("")
    L.append("## 字符串块 2 —— 游戏对象名候选（%d）" % len(rep["game_object_name_candidates"]))
    L.append("")
    L.append("| 偏移 | 名称 | 绝对引用 | 相对引用 |")
    L.append("| --- | --- | --- | --- |")
    for e in rep["game_object_name_candidates"]:
        L.append("| 0x%x | `%s` | %s | %s |" % (
            e["offset"], e["name"],
            ", ".join(e["referenced_absolute"]) or "-",
            ", ".join(e["referenced_relative_to_strings_end"]) or "-"))
    L.append("")
    L.append("## 已知未知项")
    L.append("")
    for u in rep["known_unknowns"]:
        L.append("- %s" % u)
    L.append("")
    L.append("> %s" % rep["classification_caveat"])
    L.append("")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description="解析 RE Engine PFB 的源资源引用图（只读研究工具）")
    ap.add_argument("pfb")
    ap.add_argument("--json")
    ap.add_argument("--md")
    ap.add_argument("--allow-version", action="append", default=[], metavar="N",
                    help="研究用：额外接受该 PFB 版本做只读结构探测（可重复）")
    args = ap.parse_args(argv)

    allowed = (SUPPORTED_PFB_VERSION,) + tuple(int(v, 0) for v in args.allow_version)
    try:
        rep = parse_pfb(Path(args.pfb).read_bytes(), source=str(args.pfb),
                        allowed_versions=allowed)
    except ManualReviewRequired as exc:
        print("MANUAL_REVIEW_REQUIRED")
        print("  " + str(exc))
        return 2

    if args.json:
        p = Path(args.json)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(rep, indent=2, ensure_ascii=False) + "\n")
    if args.md:
        p = Path(args.md)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(render_md(rep))

    print("PFB 解析 PASS  version=%d  size=%d" % (rep["version"], rep["file_size"]))
    print("path_table=%d  typed_refs=%d" % (len(rep["path_table"]), len(rep["typed_refs"])))
    print("猎人脸部运行时引用：%d" % len(rep["hunter_face_runtime_present"]))
    for p in rep["hunter_face_runtime_present"]:
        print("   %s" % p)
    print("游戏对象名候选：%s" % ", ".join(e["name"] for e in rep["game_object_name_candidates"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

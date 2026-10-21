#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase A/B —— inventory、依赖分类、自引用门禁、skeleton-carrier 判定。

对应 `docs/NPC_TO_PLAYER_CONVERSION_WORKFLOW_v0.2-draft.md` Phase A / Phase B
与 `MESH_LuaBone_DS_Review_2026-09-24.md` §10、§12。

Phase A：只读遍历解压目录，输出 source-tree.txt + inventory.json，按
MESH / MDF2 / TEX / CHAIN / USER / PFB / JCNS / EFX / LUA / OTHER 分类。
不修改任何源文件。

Phase B：
  1. **自引用门禁**（唯一可能推翻"直接改名"策略的一步）。Golden 的做法是把
     NPC 资源改文件名搬进私有目录、内容零改动（`static-validation.json` 证实
     byte-identical）。这只有在资源内部不引用自身/同族资源名时才成立。本工具
     按 ASCII + UTF-16LE 双编码扫描包内每一个文件，报告：
       - self_reference  ：文件内容含自身资源基名
       - cross_reference ：文件内容含同包其他资源基名
       - ext_reference   ：文件内容含 .mesh/.mdf2/.chain/.jcns/.user/.tex 引用
     命中且不在 --exclude 范围内的资源基名 -> gate = MANUAL_REVIEW_REQUIRED。
  2. **资源组织形态判定**（审查意见 §10）。官方 NPC 的模型组织不统一，可能是
     SPLIT / SINGLE-CARRIER / HYBRID，所以 LuaBone 工具不接受 "body mesh"
     这种语义输入，必须先判定哪个 mesh 是 PRIMARY_VISUAL / SKELETON_CARRIER。
     判定方式：对每个 .mesh 尝试 mesh_skeleton 解析，只有 version 0x014111C0
     会被接受；关节数最大者作为 carrier 候选。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mesh_skeleton import ManualReviewRequired, parse_mesh_skeleton  # noqa: E402

CATEGORY_BY_EXT = {
    "mesh": "MESH",
    "mdf2": "MDF2",
    "tex": "TEX",
    "chain": "CHAIN",
    "user": "USER",
    "pfb": "PFB",
    "jcns": "JCNS",
    "efx": "EFX",
    "lua": "LUA",
    "mot": "MOT",
    "motlist": "MOTLIST",
    "json": "JSON",
    "rcol": "RCOL",
}

EXT_REFERENCE_TOKENS = (".mesh", ".mdf2", ".chain", ".jcns", ".user", ".tex", ".pfb", ".efx")


def split_version_suffix(name):
    """`npc709_01_body.mesh.2109148288` -> ('npc709_01_body', 'mesh', '2109148288')。"""
    bits = name.split(".")
    if len(bits) >= 3 and bits[-1].isdigit():
        return ".".join(bits[:-2]), bits[-2], bits[-1]
    if len(bits) == 2:
        return bits[0], bits[1], None
    return name, None, None


def asset_stem(path):
    """只对带版本后缀的 RE Engine 资源返回基名。

    `1.jpg` / `modinfo.ini` 这类文件返回 None —— 否则单字符基名会在二进制里
    必然命中，制造纯噪音的门禁告警。
    """
    stem, _, ver = split_version_suffix(path.name)
    if ver is None:
        return None
    return stem


def categorize(path):
    _, ext, _ = split_version_suffix(path.name)
    if path.suffix.lower() == ".lua":
        return "LUA"
    return CATEGORY_BY_EXT.get((ext or "").lower(), "OTHER")


def scan_bytes(data, patterns):
    """双编码扫描，返回 {pattern: {encoding: [offsets]}}。"""
    hits = {}
    for pat in patterns:
        for enc in ("ascii", "utf-16-le"):
            try:
                needle = pat.encode(enc)
            except UnicodeEncodeError:
                continue
            offs, start = [], 0
            while True:
                i = data.find(needle, start)
                if i < 0:
                    break
                offs.append(i)
                start = i + 1
                if len(offs) >= 500:
                    break
            if offs:
                hits.setdefault(pat, {})[enc] = offs
    return hits


def build_inventory(source_root, exclude=(), rename_targets=()):
    source_root = Path(source_root)
    files = sorted(p for p in source_root.rglob("*") if p.is_file())
    rename_targets = set(rename_targets)

    # 扫描模式只来自"真实资源基名"与足够的目录名；短名/纯数字一律不参与，
    # 否则会在二进制里必然命中。
    stems = {}
    for p in files:
        s = asset_stem(p)
        if s:
            stems.setdefault(s, []).append(p.relative_to(source_root).as_posix())
        for d in p.relative_to(source_root).parts[:-1]:
            if len(d) >= 5 and "." not in d:
                stems.setdefault(d, []).append(p.relative_to(source_root).as_posix())

    exclude_set = set(exclude)
    scan_patterns = sorted(set(stems))
    recent = list(EXT_REFERENCE_TOKENS)

    entries, categories = [], {}
    for p in files:
        rel = p.relative_to(source_root).as_posix()
        cat = categorize(p)
        categories.setdefault(cat, []).append(rel)
        data = p.read_bytes()
        hits = scan_bytes(data, scan_patterns + recent)

        own = asset_stem(p)
        self_ref, cross_ref, ext_ref = [], [], []
        for pat, encs in hits.items():
            offs = sum(len(v) for v in encs.values())
            rec = {"token": pat, "count": offs,
                   "encodings": sorted(encs),
                   "first_offsets": sorted(
                       {o for v in encs.values() for o in v})[:8]}
            if pat in EXT_REFERENCE_TOKENS:
                ext_ref.append(rec)
            elif own is not None and pat == own:
                self_ref.append(rec)
            else:
                cross_ref.append(rec)

        entries.append({
            "path": rel,
            "size": len(data),
            "category": cat,
            "asset_stem": own,
            "excluded": rel in exclude_set,
            "self_reference": self_ref,
            "cross_reference": cross_ref,
            "ext_reference": ext_ref,
        })

    # skeleton-carrier 判定
    carriers, mesh_failures = [], []
    for e in entries:
        if e["category"] != "MESH":
            continue
        p = source_root / e["path"]
        try:
            sk = parse_mesh_skeleton(p.read_bytes(), source=e["path"])
        except ManualReviewRequired as exc:
            mesh_failures.append({"path": e["path"], "reason": str(exc)})
            continue
        carriers.append({
            "path": e["path"],
            "joint_count": sk.joint_count,
            "mesh_version": "0x%08X" % sk.version,
            "materials": sk.material_names,
        })

    carriers.sort(key=lambda c: c["joint_count"], reverse=True)
    if len(carriers) == 1:
        org = "SINGLE-CARRIER"
    elif len(carriers) > 1:
        org = "SPLIT-or-HYBRID (需要人工确认 PRIMARY_VISUAL / SKELETON_CARRIER)"
    else:
        org = "NO-CARRIER"

    # 门禁：精确针对"将被改名的资源"
    gate_reasons = []
    if rename_targets:
        for e in entries:
            if e["excluded"]:
                continue
            hit = sorted({r["token"] for r in e["self_reference"] + e["cross_reference"]
                          if r["token"] in rename_targets})
            if hit:
                gate_reasons.append(
                    "%s: 内容引用了将被改名的资源 %s —— 改名后可能断链，需人工确认"
                    % (e["path"], hit))
    else:
        for e in entries:
            if e["excluded"]:
                continue
            if e["self_reference"]:
                gate_reasons.append(
                    "%s: 内容含自身资源基名 %s —— 改名后可能断链"
                    % (e["path"], [r["token"] for r in e["self_reference"]]))
    if not carriers:
        gate_reasons.append("没有任何 mesh 能通过 mesh_skeleton 解析，无法确定 skeleton-carrier")
    elif len(carriers) > 1:
        gate_reasons.append(
            "存在多个可解析 skeleton-carrier mesh（%s），需人工确认" % [c["path"] for c in carriers])

    return {
        "source_root": str(source_root),
        "file_count": len(files),
        "categories": {k: sorted(v) for k, v in sorted(categories.items())},
        "asset_stems": {k: sorted(set(v)) for k, v in sorted(stems.items())},
        "excluded": sorted(exclude_set),
        "rename_targets": sorted(rename_targets),
        "entries": entries,
        "skeleton_carrier": {
            "organization": org,
            "candidates": carriers,
            "unparseable_meshes": mesh_failures,
            "selected": carriers[0]["path"] if len(carriers) == 1 else None,
        },
        "gate": {
            "result": "PASS" if not gate_reasons else "MANUAL_REVIEW_REQUIRED",
            "reasons": gate_reasons,
        },
    }


def write_source_tree(inventory, path):
    lines = ["size_bytes\tcategory\tpath"]
    for e in inventory["entries"]:
        lines.append("%d\t%s\t%s" % (e["size"], e["category"], e["path"]))
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    return p


def main(argv=None):
    ap = argparse.ArgumentParser(description="Phase A/B：inventory + 自引用门禁 + skeleton-carrier 判定")
    ap.add_argument("--source", required=True, help="NPC mod 解压目录")
    ap.add_argument("--out-dir", required=True, help="报告输出目录（通常是 work/<task>/reports/）")
    ap.add_argument("--exclude", action="append", default=[],
                    help="不参与门禁判定的相对路径（可重复）")
    ap.add_argument("--rename-target", action="append", default=[],
                    help="将被改名的资源基名（可重复）。门禁会检查除 --exclude 外的"
                         "任何文件是否引用它")
    args = ap.parse_args(argv)

    inv = build_inventory(args.source, exclude=args.exclude,
                          rename_targets=args.rename_target)
    out_dir = Path(args.out_dir)

    inv_path = out_dir / "inventory.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(inv_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(inv, indent=2, ensure_ascii=False) + "\n")
    tree_path = write_source_tree(inv, out_dir / "source-tree.txt")

    print("Phase A/B inventory")
    print("  source        : %s" % inv["source_root"])
    print("  files         : %d" % inv["file_count"])
    for cat, items in inv["categories"].items():
        print("    %-8s %d" % (cat, len(items)))
    print("  org           : %s" % inv["skeleton_carrier"]["organization"])
    for c in inv["skeleton_carrier"]["candidates"]:
        print("    carrier     : %s  J=%d  %s" % (c["path"], c["joint_count"], c["mesh_version"]))
    for f in inv["skeleton_carrier"]["unparseable_meshes"]:
        print("    non-carrier : %s" % f["path"])
    print("  excluded      : %s" % inv["excluded"])
    print("  rename targets: %s" % inv["rename_targets"])
    print("  GATE          : %s" % inv["gate"]["result"])
    for r in inv["gate"]["reasons"]:
        print("    - %s" % r)
    print("  inventory     : %s" % inv_path)
    print("  source-tree   : %s" % tree_path)

    return 0 if inv["gate"]["result"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NPC 外观包形态普查 —— 只读研究工具（2026-09-25）。

目的
----
对**整个 NPC 外观包系列**做结构普查，回答"文件结构是否存在客观分类维度"，
而不是从少数样本归纳。判定全部基于**路径与文件名**，不做语义猜测。

扫描的维度（每个包一行）
------------------------
- `npc_id`      `npc/mod/npcXXX_00/` 里的 NPC 编号
- `prefab_dir`  PFB 所在子目录（如 `a00` / `v02a00`），无 PFB 则为 None
- `player_face` 是否提供 `player/mod/face/pl_faceNNN.mesh`
- `player_hair` 是否提供 `player/mod/<f|m>/hair/<slot>/n_hairNNN.mesh`，记录性别与槽号
- `npc_face`    NPC 侧 `npcXXX_00_face/` 下的文件数与扩展名
- `npc_hair`    NPC 侧 `npcXXX_00_hair/` 下的文件数与扩展名
- `body_stem`   body mesh 的资源基名（`npcXXX_00_body` vs `npcXXX_01_body`）
- `chain`       chain 文件的完整基名与所在目录
- `armor_set`   是否走"改本体现成装备"形态（`player/mod/<f|m>/plNNN/`）
- `luabone`     `reframework/data/LUABoneSystem/custom/` 下的 JSON 名
- `textures`    `dddder4/npcXXX/` 下的贴图基名（含子目录深度）
- `dd_extra_dir` 贴图目录是否多一层（`dddder4/npcXXX/nidXXX/`）

只读保证：本工具只 `os.walk` + 读文件名，不打开、不修改任何资源文件。

用法
----
    python scripts/survey_npc_variants.py <mods_root> --json <out.json> [--md <out.md>]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PREFIX = "natives/STM/"

NPC_DIR = re.compile(r"^npc/mod/(npc\d+)_00/")
PREFAB = re.compile(r"^npc/prefab/([^/]+)/(nid\d+)\.pfb")
PLAYER_FACE = re.compile(r"^player/mod/face/pl_face(\d+)\.mesh")
PLAYER_HAIR = re.compile(r"^player/mod/(f|m)/hair/([^/]+)/n_hair(\d+)\.mesh")
ARMOR_SET = re.compile(r"^player/mod/(f|m)/(pl\d+)/")
LUABONE = re.compile(r"^reframework/data/LUABoneSystem/custom/(.+\.json)$")
NPC_TEX = re.compile(r"^dddder4/(npc\d+)/(.*)$")


def norm(rel):
    return rel.replace("\\", "/")


def survey_package(root):
    root = Path(root)
    paths = []
    for p in root.rglob("*"):
        if p.is_file():
            rel = norm(str(p.relative_to(root)))
            if rel.startswith(PREFIX):
                paths.append(rel[len(PREFIX):])
    rec = {
        "mod": root.name,
        "npc_id": None,
        "prefab_dir": None,
        "prefab_name": None,
        "player_face": None,
        "player_hair": None,
        "npc_face": [],
        "npc_hair": [],
        "body_meshes": [],
        "chain_files": [],
        "armor_set": None,
        "luabone": [],
        "textures": [],
        "tex_extra_subdir": False,
        "n_paths": len(paths),
    }
    for rel in sorted(paths):
        m = NPC_DIR.match(rel)
        if m:
            rec["npc_id"] = rec["npc_id"] or m.group(1)
        m = PREFAB.match(rel)
        if m:
            rec["prefab_dir"] = m.group(1)
            rec["prefab_name"] = m.group(2)
        m = PLAYER_FACE.match(rel)
        if m:
            rec["player_face"] = "pl_face%s.mesh" % m.group(1)
        m = PLAYER_HAIR.match(rel)
        if m:
            rec["player_hair"] = "%s/%s/n_hair%s.mesh" % (m.group(1), m.group(2), m.group(3))
        m = ARMOR_SET.match(rel)
        if m:
            rec["armor_set"] = "%s/%s" % (m.group(1), m.group(2))
        m = LUABONE.match(rel)
        if m:
            rec["luabone"].append(m.group(1))
        m = NPC_TEX.match(rel)
        if m:
            rec["textures"].append(m.group(2))
            if "/" in m.group(2):
                rec["tex_extra_subdir"] = True
        if re.search(r"_00_face/", rel) and rel.endswith(".mesh.2109148288"):
            rec["npc_face"].append(Path(rel).name.split(".mesh")[0])
        if re.search(r"_00_hair/", rel) and rel.endswith((".mesh.2109148288", ".mdf2.23")):
            rec["npc_hair"].append(Path(rel).name.split(".mesh")[0].split(".mdf2")[0]
                                   + ("[mesh]" if rel.endswith(".mesh.2109148288") else "[mdf2]"))
        if rel.endswith(".mesh.2109148288") and "_00_body/" in rel:
            rec["body_meshes"].append(Path(rel).name.split(".mesh")[0])
        if ".chain." in rel:
            rec["chain_files"].append(Path(rel).name.split(".chain")[0])

    # 结构形态标签（由客观字段导出，不做语义推断）
    tags = []
    if rec["armor_set"]:
        tags.append("ARMOR_SET_INPLACE")
    if rec["prefab_dir"]:
        tags.append("NPC_PREFAB_OVERRIDE")
    if rec["player_face"]:
        tags.append("PLAYER_FACE_SLOT")
    if rec["player_hair"]:
        tags.append("PLAYER_HAIR_SLOT")
    if not rec["prefab_dir"] and not rec["armor_set"]:
        tags.append("PATH_OVERRIDE_ONLY")
    rec["tags"] = tags
    rec["head_layer_side"] = (
        "player_slot" if (rec["player_face"] or rec["player_hair"])
        else ("npc_side" if (rec["npc_face"] or rec["npc_hair"]) else "absent")
    )
    return rec


def render_md(recs):
    L = ["# NPC 外观包形态普查", "",
         "| mod | npc_id | prefab 目录 | 玩家脸槽 | 玩家发槽 | NPC 侧 face | NPC 侧 hair | body 基名 | chain 基名 | 贴图 | LuaBone | tags |",
         "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in recs:
        L.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %d | %s | %s |" % (
            r["mod"], r["npc_id"] or "-", r["prefab_dir"] or "-",
            r["player_face"] or "-", r["player_hair"] or "-",
            ", ".join(r["npc_face"]) or "-", ", ".join(r["npc_hair"]) or "-",
            ", ".join(r["body_meshes"]) or "-", ", ".join(r["chain_files"]) or "-",
            len(r["textures"]), ", ".join(r["luabone"]) or "-", ", ".join(r["tags"])))
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="NPC 外观包形态普查（只读）")
    ap.add_argument("root", help="mod 库根目录（每个子目录是一个包）")
    ap.add_argument("--json")
    ap.add_argument("--md")
    ap.add_argument("--filter", default="", help="只包含名字含该子串的包")
    args = ap.parse_args(argv)

    root = Path(args.root)
    recs = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        if args.filter and args.filter.lower() not in child.name.lower():
            continue
        if not (child / "natives").exists():
            continue
        recs.append(survey_package(child))

    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(recs, indent=2, ensure_ascii=False) + "\n",
                                   encoding="utf-8", newline="\n")
    if args.md:
        Path(args.md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.md).write_text(render_md(recs), encoding="utf-8", newline="\n")

    print("扫描 %d 个包" % len(recs))
    from collections import Counter
    print("  prefab 目录分布 :", dict(Counter(r["prefab_dir"] for r in recs)))
    print("  head_layer_side :", dict(Counter(r["head_layer_side"] for r in recs)))
    print("  tags 分布       :", dict(Counter(t for r in recs for t in r["tags"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

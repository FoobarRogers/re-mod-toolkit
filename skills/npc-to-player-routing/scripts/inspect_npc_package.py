#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NPC mod 包结构清点 —— 只读研究工具（NPC4 系列首次使用，2026-09-25）。

目的
----
回答"这个 NPC 包到底由哪些层构成、每一层绑在哪里"，供 NPC → Player 转换前
判定**资源闭包**与**槽位绑定策略**。它不是打包工具，也不改写任何资源。

输出（JSON 一份）
-----------------
1. `files`            —— 逐文件 sha256 + 大小
2. `meshes`           —— 每个 .mesh.* 的版本 / 关节数 / 材质名 / 关节名，
                        与 `base/f_shadow.json` 的命中与差集；
                        新版本以 `--allow-version` 显式放开（默认只认生产已验证版本）
3. `materials`        —— 每个 .mdf2.* 的材质名、贴图路径、嵌入的 chain 标识
4. `prefabs`          —— 每个 .pfb.* 的引用表（绝对 + 相对两套寻址），并分类
5. `binding_strategy` —— 由**路径**判定该包把"脸/发"绑在 NPC 侧还是玩家侧。
                        这是结构性判据，直接决定转换时要不要额外搬玩家槽位资源
6. `notes`            —— 明确列出本工具**没有**判定的东西（不猜）

用法
----
    python scripts/inspect_npc_package.py <package_root> --json <out.json> \
        [--allow-version 0x014160A8] [--allow-version 0x0141D2B8] \
        [--allow-pfb-version 6] [--label npc005]

`<package_root>` 是解压后的包根目录（含 `natives/` 的那一层）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mesh_skeleton import ManualReviewRequired, parse_mesh_skeleton  # noqa: E402
from inspect_npc_pfb import parse_pfb  # noqa: E402

_U16_RUN = re.compile(rb"(?:[\x20-\x7e]\x00){4,}")

# 玩家侧槽位路径：这两条是"猎人型 NPC"复用玩家头部框架的直接证据
# 注意：包内文件名带版本后缀（`pl_face746.mesh.2109148288`），而 PFB 引用不带。
_VER = r"(?:\.\d+)?"
PLAYER_FACE_SLOT = re.compile(r"^player/mod/face/pl_face(\d+)\.mesh" + _VER + r"$")
PLAYER_HAIR_SLOT = re.compile(r"^player/mod/f/hair/(f_hair\d+)/n_hair(\d+)\.mesh" + _VER + r"$")
NPC_FACE_RES = re.compile(r"^npc/mod/(npc\d+)_00/(npc\d+_00_face)/[\w.]+\.mesh" + _VER + r"$")

FAMILY_SUFFIX = (
    "mesh", "mdf2", "chain", "pfb", "tex", "user", "jcns", "motbank", "msg",
    "jmap", "jointlodgroup", "iklookat2", "fsmv2", "motfsm2", "gui", "wcc", "rcol",
)


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def split_family(name):
    """`npc005_00_body.mesh.2109148288` -> ('npc005_00_body', 'mesh', '2109148288')"""
    parts = name.split(".")
    if len(parts) >= 3 and parts[-2] in FAMILY_SUFFIX:
        return ".".join(parts[:-2]), parts[-2], parts[-1]
    if len(parts) >= 2 and parts[-1] in FAMILY_SUFFIX:
        return ".".join(parts[:-1]), parts[-1], None
    return name, None, None


def u16_strings(data):
    return sorted({m.group().decode("utf-16-le") for m in _U16_RUN.finditer(data)})


def mesh_report(path, allowed_versions):
    data = path.read_bytes()
    rep = {
        "path": None,
        "size": len(data),
        "magic": data[:4].decode("latin-1"),
        "magic_is_MESH": data[:4] == b"MESH",
        "version": "0x%08X" % struct.unpack_from("<I", data, 4)[0] if len(data) >= 8 else None,
        "parse": "SKIPPED",
    }
    if not rep["magic_is_MESH"]:
        rep["parse"] = "NOT_A_MESH_magic"
        rep["magic_hex"] = " ".join("%02X" % b for b in data[:4])
        return rep
    try:
        sk = parse_mesh_skeleton(data, source=path.name, allowed_versions=allowed_versions)
    except ManualReviewRequired as exc:
        rep["parse"] = "MANUAL_REVIEW_REQUIRED"
        rep["reason"] = str(exc)
        return rep
    rep.update({
        "parse": "PASS",
        "joint_count": sk.joint_count,
        "material_names": sk.material_names,
        "joint_names": sk.joint_names,
        "parent_array_offset": sk.parent_array_offset,
        "matrix_array_offset": sk.matrix_array_offset,
        "invariant_failures": [j.name for j in sk.joints if not j.invariants_ok],
        "warnings": sk.warnings,
    })
    return rep


def mdf2_report(path, data):
    strings = u16_strings(data)
    materials = []
    textures = []
    chains = []
    mmtr = []
    for s in strings:
        if s.endswith(".tex") or s.endswith(".tex.28"):
            textures.append(s)
        elif s.endswith(".mmtr"):
            mmtr.append(s)
        elif re.search(r"\.chain\b", s):
            chains.append(s)
        elif "/" not in s and not s.endswith(".tex") and not s.startswith("Master"):
            materials.append(s)
    return {
        "size": len(data),
        "internal_version": struct.unpack_from("<I", data, 4)[0],
        "material_names": materials,
        "texture_paths": textures,
        "chain_refs": chains,
        "master_materials": mmtr,
        "all_u16_strings": strings,
    }


def pfb_report(path, data, allowed_versions):
    try:
        rep = parse_pfb(data, source=path.name, allowed_versions=allowed_versions)
    except ManualReviewRequired as exc:
        return {"parse": "MANUAL_REVIEW_REQUIRED", "reason": str(exc)}
    paths = [e["path"] for e in rep["path_table"]] + [e["path"] for e in rep["typed_refs"]]
    return {
        "parse": "PASS",
        "version": rep["version"],
        "path_table": [e["path"] for e in rep["path_table"]],
        "typed_refs": [{"class_hash": e["class_hash"], "path": e["path"]} for e in rep["typed_refs"]],
        "all_referenced_paths": paths,
        "game_object_name_candidates": rep["game_object_name_candidates"],
        "hunter_face_runtime_present": rep["hunter_face_runtime_present"],
    }


def classify_binding(paths, files):
    """由路径判定脸/发资源的绑定侧。结构性判据，不做语义猜测。"""
    player_face = [p for p in paths if PLAYER_FACE_SLOT.match(p)]
    player_hair = [p for p in paths if PLAYER_HAIR_SLOT.match(p)]
    npc_face = [p for p in paths if NPC_FACE_RES.match(p)]
    files_player_face = [f for f in files if PLAYER_FACE_SLOT.match(f.split("natives/STM/", 1)[-1])]
    files_player_hair = [f for f in files if PLAYER_HAIR_SLOT.match(f.split("natives/STM/", 1)[-1])]
    files_npc_face = [f for f in files if NPC_FACE_RES.match(f.split("natives/STM/", 1)[-1])]
    return {
        "pfb_references_player_face_slot": player_face,
        "pfb_references_player_hair_slot": player_hair,
        "pfb_references_npc_side_face": npc_face,
        "package_ships_player_face_slot_mesh": files_player_face,
        "package_ships_player_hair_slot_mesh": files_player_hair,
        "package_ships_npc_side_face_mesh": files_npc_face,
        "face_layer_binding": (
            "player_slot" if (player_face or files_player_face)
            else ("npc_side" if (npc_face or files_npc_face) else "absent")
        ),
        "hair_layer_binding": (
            "player_slot" if (player_hair or files_player_hair)
            else ("npc_side" if any("_hair" in f and f.endswith((".mesh", ".mdf2")) for f in files)
                  else "absent")
        ),
    }


def inspect(root, label, allowed_mesh_versions, allowed_pfb_versions, shadow_path):
    root = Path(root)
    files = []
    meshes = {}
    materials = {}
    prefabs = {}
    all_labels = []

    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(root)).replace("\\", "/")
        rec = {
            "path": rel,
            "size": p.stat().st_size,
            "sha256": sha256_of(p),
        }
        family = None
        if rel.endswith(".mesh.2109148288"):
            family = "mesh"
        elif rel.endswith(".mdf2.23"):
            family = "mdf2"
        elif rel.endswith(".pfb.17"):
            family = "pfb"
        elif ".chain." in rel:
            family = "chain"
        elif ".tex." in rel:
            family = "tex"
        rec["family"] = family
        files.append(rec)
        if family == "mesh":
            all_labels.append(rel)
            r = mesh_report(p, allowed_mesh_versions)
            r["path"] = rel
            meshes[rel] = r
        elif family == "mdf2":
            materials[rel] = mdf2_report(p, p.read_bytes())
            materials[rel]["path"] = rel
        elif family == "pfb":
            r = pfb_report(p, p.read_bytes(), allowed_pfb_versions)
            r["path"] = rel
            prefabs[rel] = r

    shadow_keys = []
    if shadow_path and Path(shadow_path).exists():
        shadow = json.loads(Path(shadow_path).read_text(encoding="utf-8"))
        shadow_keys = list(shadow.keys())
    slow = {k.lower() for k in shadow_keys}
    for rel, r in meshes.items():
        if r.get("parse") != "PASS":
            continue
        low = [n.lower() for n in r["joint_names"]]
        r["f_shadow_keys"] = len(shadow_keys)
        r["f_shadow_matched"] = sum(1 for n in low if n in slow)
        r["missing_in_mesh"] = sorted(n for n in slow if n not in set(low))
        r["mesh_only"] = [r["joint_names"][i] for i, n in enumerate(low) if n not in slow]

    pfb_paths = []
    for r in prefabs.values():
        pfb_paths.extend(r.get("all_referenced_paths", []))
    file_rels = [f["path"] for f in files]
    file_rels_stripped = [f.split("natives/STM/", 1)[-1] for f in file_rels]

    layout = {
        "has_pfb": bool(prefabs),
        "has_body_mesh": any("_body.mesh" in f for f in file_rels),
        "has_hair_mesh": any("_hair.mesh" in f for f in file_rels),
        "has_face_mesh": any("_face.mesh" in f or "pl_face" in f for f in file_rels),
        "has_body_chain": any("_body.chain" in f for f in file_rels),
        "has_player_side_resources": any("/player/" in f for f in file_rels),
        "texture_roots": sorted({"/".join(f.split("/")[:3]) for f in file_rels if f.endswith(".tex.28")}),
    }

    return {
        "label": label,
        "root": str(root),
        "file_count": len(files),
        "files": files,
        "layout": layout,
        "meshes": meshes,
        "materials": materials,
        "prefabs": prefabs,
        "binding_strategy": classify_binding(pfb_paths, file_rels_stripped),
        "notes": [
            "本工具只做结构清点，不判定任何资源的可丢弃性。",
            "binding_strategy 由路径判定；无 PFB 的包只能给出『包内实际放置位置』，"
            "不能证明运行时绑定（vanilla prefab 不在此包内）。",
            "mdf2 的 material_names 由字符串启发式得出，仅用于与 mesh 的材质名对齐。",
            "geometry/顶点缓冲未解析；mesh 的几何范围属 UNKNOWN。",
        ],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="NPC mod 包结构清点（只读研究工具）")
    ap.add_argument("root", help="解压后的包根目录（含 natives/ 的那一层）")
    ap.add_argument("--label", default=None)
    ap.add_argument("--json")
    ap.add_argument("--f-shadow", default=str(Path(__file__).resolve().parent.parent / "base" / "f_shadow.json"))
    ap.add_argument("--allow-version", action="append", default=[], metavar="0xXXXXXXXX",
                    help="研究用：额外接受该 MESH 版本做只读解析（可重复）")
    ap.add_argument("--allow-pfb-version", action="append", default=[], metavar="N",
                    help="研究用：额外接受该 PFB 版本做只读解析（可重复）")
    args = ap.parse_args(argv)

    from mesh_skeleton import SUPPORTED_MESH_VERSION
    from inspect_npc_pfb import SUPPORTED_PFB_VERSION

    mesh_versions = (SUPPORTED_MESH_VERSION,) + tuple(int(v, 0) for v in args.allow_version)
    pfb_versions = (SUPPORTED_PFB_VERSION,) + tuple(int(v, 0) for v in args.allow_pfb_version)

    rep = inspect(args.root, args.label or Path(args.root).name, mesh_versions, pfb_versions,
                  args.f_shadow)

    if args.json:
        p = Path(args.json)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(rep, indent=2, ensure_ascii=False) + "\n")

    print("== %s ==" % rep["label"])
    print("  文件 %d，PFB %s，玩家侧资源 %s" % (
        rep["file_count"], rep["layout"]["has_pfb"], rep["layout"]["has_player_side_resources"]))
    print("  脸层绑定 = %s   发层绑定 = %s" % (
        rep["binding_strategy"]["face_layer_binding"], rep["binding_strategy"]["hair_layer_binding"]))
    for rel, r in rep["meshes"].items():
        print("  MESH %-62s %s" % (rel.split("natives/STM/")[-1], r.get("parse")))
        if r.get("parse") == "PASS":
            print("       ver=%s J=%d materials=%s" % (r["version"], r["joint_count"],
                                                       r["material_names"]))
            print("       f_shadow 命中 %d/%d，mesh-only %d" % (
                r["f_shadow_matched"], r["f_shadow_keys"], len(r["mesh_only"])))
        elif r.get("reason"):
            print("       %s" % r["reason"])
    for rel, r in rep["prefabs"].items():
        print("  PFB  %-62s %s" % (rel, r.get("parse")))
        if r.get("parse") == "PASS":
            print("       version=%s refs=%d" % (r["version"], len(r["all_referenced_paths"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

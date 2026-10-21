#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按分类类型构建独立 Test Package —— 参数化构建器（Research Test 用）。

对应 `TODO_WORKFLOW_Taxonomy_Runtime_Validation_v0.1-draft.md` TODO 06 / 07。

设计目的
--------
既有的 `scripts/npc2player.py` **硬编码了 Golden 的槽绑定模式**
（`wst` 承载真模型、`arm/body/helm` dummy、`f_leg` 复用 arm）。
TODO 06 明令禁止把这个习惯套到所有类型上：

```text
A1/A2：不得因 Golden 习惯自动把全部模型塞入 wst
B1  ：优先尊重源 Follower / Armor Set 已存在的真实 carrier slot
C1  ：不得为了维持 "Workflow C" 强行制造独立输出路线
```

所以本工具**不假设任何槽位**：每个 Test 通过 spec JSON 显式声明
"哪个槽放什么"。它只做确定性动作，不做语义推断。

spec JSON 契约
--------------
```json
{
  "label": "A1_DaiwaScarlet",
  "asset_id": "J019",
  "slot": "423",
  "source": "research/.../A1_DaiwaScarlet/work/source",
  "modinfo_name": "...",
  "version": "test1",
  "prefab": {                                   // 私有资源路线才有
    "template_dir": "base/golden/J017_AstonMachan_R1/mod/natives/STM/player/prefab/mod/f/pl423",
    "rewrite": [["JRRB/J017", "JRRB/J019"], ["JRarm017", "JRarm019"], ...],
    "filename_rewrite": []
  },
  "private": {                                  // null = 不使用 JRRB 私有命名
    "dir": "player/JRRB/J019",
    "carriers": [                               // 每个槽 → 源 mesh 基名（相对 source/natives/STM）
      {"role": "wst", "stem": "npc/mod/npc714_00/npc714_00_body/npc714_00_body",
       "rename": "JRwst019", "lua_bone_from": "mesh"},
      {"role": "arm", "dummy": true, "rename": "JRarm019", "lua_bone_from": "mesh"}
    ],
    "leg_reuses": "arm"
  },
  "head_layer": [                               // 逐字节搬运（同路径或改名由 dst 决定）
    {"src": "player/mod/face/pl_face714.mesh.2109148288",
     "dst": "player/mod/face/pl_face714.mesh.2109148288"}
  ],
  "textures": ["dddder4/npc714"],               // 原路径保留的贴图目录
  "allow_mesh_version": ["0x014160A8", "0x0141D2B8"],
  "allow_pfb_version": [1, 6, 9]
}
```

本工具**不做**：可丢弃性判定、语义推断、实机断言。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from mesh_skeleton import (  # noqa: E402
    SUPPORTED_MESH_VERSION,
    ManualReviewRequired,
    parse_mesh_skeleton,
)
from luabone_generate import MISSING_POLICY, generate as luabone_generate  # noqa: E402
from luabone_generate import dump_json as luabone_dump  # noqa: E402
from pfb_equal_length_replace import run as pfb_rewrite  # noqa: E402
from verify_package_refs import check_package  # noqa: E402


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        p.write_text(data, encoding="utf-8", newline="\n")
    else:
        p.write_bytes(data)


def mesh_versions_in(root, allowed):
    """扫描源里所有 mesh 的版本，返回 {version: [paths]}，并标注是否在允许集合内。"""
    out = {}
    for p in Path(root).rglob("*.mesh.2109148288"):
        b = p.read_bytes()
        if b[:4] != b"MESH":
            out.setdefault("NOT_MESH", []).append(str(p))
            continue
        v = struct.unpack_from("<I", b, 4)[0]
        out.setdefault("0x%08X" % v, []).append(str(p))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="按类型参数化构建 Test Package")
    ap.add_argument("spec")
    ap.add_argument("--out", required=True, help="包输出目录（顶层，含 modinfo.ini）")
    ap.add_argument("--report-dir", required=True)
    args = ap.parse_args(argv)

    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    src = Path(spec["source"])
    src_natives = src / "natives" / "STM"
    out = Path(args.out)
    rep = Path(args.report_dir)
    rep.mkdir(parents=True, exist_ok=True)
    if out.exists():
        shutil.rmtree(out)
    out_natives = out / "natives" / "STM"
    out_natives.mkdir(parents=True)

    log = {"label": spec["label"], "asset_id": spec["asset_id"], "slot": spec.get("slot"),
           "source": str(src), "added": [], "modified": [], "renamed": [],
           "unchanged": [], "lua_bone": {}, "notes": []}

    # ---------- 0) mesh 版本体检 ----------
    # 门禁只约束**需要被解析**的 mesh（= 承载件，要拿来算 LuaBone）。
    # 只做逐字节复制的资源（头部层 / 贴图 / 保真复制）不解析，因此新版本对它们
    # 不是风险，但也必须**登记并报告**（TODO 08：研究 Test 可登记使用，不等于进生产支持）。
    allowed = (SUPPORTED_MESH_VERSION,) + tuple(int(v, 0) for v in spec.get("allow_mesh_version", []))
    registered = allowed + tuple(int(v, 0) for v in spec.get("register_mesh_version", []))
    mv = mesh_versions_in(src, allowed)
    log["source_mesh_versions"] = {k: sorted(Path(x).name for x in v) for k, v in mv.items()}

    carrier_stems = []
    if spec.get("private"):
        carrier_stems = [c["stem"] for c in spec["private"]["carriers"] if not c.get("dummy")]
    parse_versions = set()
    for stem in carrier_stems:
        p = src_natives / (stem + ".mesh.2109148288")
        if not p.exists():
            raise SystemExit("STOP：承载件 mesh 不存在 %s" % p)
        b = p.read_bytes()
        v = struct.unpack_from("<I", b, 4)[0]
        parse_versions.add(v)
        if v not in allowed:
            raise SystemExit(
                "STOP：承载件 %s 的 MESH 版本 0x%08X 未在 spec.allow_mesh_version 中登记；"
                "按 TODO 08，新版本必须在 Research Test 中显式登记并附结构契约证据" % (stem, v))
    log["parsed_mesh_versions"] = sorted("0x%08X" % v for v in parse_versions)
    log["notes"].append("需要解析的承载件版本：%s（全部在显式允许集合内）"
                        % ", ".join(log["parsed_mesh_versions"]))
    # 源包版本全貌只作日志：源里可能有**本包并不携带**的资源
    # （例如盟友包的 player/mod/f/plNNN 原位资源、占位件 face/hair）。
    # 真正的登记门禁在构建完成后按**产物实际携带的 mesh**复检（见 §0b）。
    log["source_mesh_versions_note"] = (
        "仅作信息；登记门禁按产物实际携带的 mesh 复检，不对源包全量强制")
    log["registered_mesh_versions"] = sorted({"0x%08X" % v for v in registered})

    # ---------- 1) 私有资源（按 spec 指定的槽绑定，不套用任何既有习惯） ----------
    private = spec.get("private")
    lua_bone_src = {}
    if private:
        pdir = out_natives / private["dir"].replace("player/", "player/")
        # private["dir"] 形如 "player/JRRB/J019"，相对 natives/STM
        pdir = out_natives / private["dir"].split("player/", 1)[1]
        pdir = out_natives / "player" / private["dir"].split("player/", 1)[1]
        pdir.mkdir(parents=True, exist_ok=True)
        for c in private["carriers"]:
            rename = c["rename"]
            if c.get("dummy"):
                tmpl = JSON_DUMMY_DIR
                for fam in ("mesh", "mdf2", "chain"):
                    s = tmpl / ("JRarm017.%s.2109148288" % fam if fam == "mesh"
                                else "JRarm017.%s.%s" % (fam, {"mdf2": "23", "chain": "48"}[fam]))
                    if not s.exists():
                        continue
                    write(pdir / ("%s.%s.%s" % (rename, fam, {"mesh": "2109148288", "mdf2": "23",
                                                              "chain": "48"}[fam])),
                          s.read_bytes())
                    log["added"].append(str((pdir / ("%s.%s" % (rename, fam))).relative_to(out)))
                # helm 另有 .user
                u = tmpl / "JRhelm017.user.2"
                if c["role"] == "helm" and u.exists():
                    write(pdir / ("%s.user.2" % rename), u.read_bytes())
                    log["added"].append(str((pdir / ("%s.user.2" % rename)).relative_to(out)))
                log["notes"].append("槽 %s：dummy（来自 Golden 的 5016 B null-visual 集）" % c["role"])
                continue
            stem = src_natives / c["stem"]
            for fam, ver in (("mesh", "2109148288"), ("mdf2", "23"), ("chain", "48")):
                s = Path(str(stem) + ".%s.%s" % (fam, ver))
                if not s.exists():
                    continue
                dst = pdir / ("%s.%s.%s" % (rename, fam, ver))
                write(dst, s.read_bytes())
                log["added"].append(str(dst.relative_to(out)))
            log["notes"].append("槽 %s：承载真模型 ← %s" % (c["role"], c["stem"]))
            if c.get("lua_bone_from", "mesh") == "mesh":
                lua_bone_src[rename] = Path(str(stem) + ".mesh.2109148288")
        if private.get("leg_reuses"):
            log["notes"].append("leg 槽复用 %s 的资源（若 spec 如此声明）" % private["leg_reuses"])

    # ---------- 2) 头部层：逐字节搬运（路径由 spec 指定） ----------
    for h in spec.get("head_layer", []):
        s = src_natives / h["src"]
        if not s.exists():
            raise SystemExit("STOP：head_layer 源不存在 %s" % s)
        dst = out_natives / h["dst"]
        write(dst, s.read_bytes())
        same = (h["src"] == h["dst"])
        log["added"].append(str(dst.relative_to(out)))
        log["notes"].append("头部层 %s（%s）" % (h["dst"], "同路径逐字节" if same else "改名逐字节"))

    # ---------- 3) 贴图：原路径保留 ----------
    for texdir in spec.get("textures", []):
        s = src_natives / texdir
        if not s.exists():
            continue
        for f in sorted(s.rglob("*")):
            if f.is_file():
                rel = f.relative_to(src_natives)
                write(out_natives / rel, f.read_bytes())
                log["added"].append(str((out_natives / rel).relative_to(out)))

    # ---------- 3b) 逐目录保真复制（B1 的"原位装备"形态：不改名、不改内容） ----------
    for cp in spec.get("copy_paths", []):
        root = src / cp if cp.startswith("reframework") else src_natives / cp
        if not root.exists():
            raise SystemExit("STOP：copy_paths 源不存在 %s" % root)
        for f in sorted(root.rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(src if cp.startswith("reframework") else src_natives)
            write(out / rel if cp.startswith("reframework") else out_natives / rel, f.read_bytes())
            log["unchanged"].append(str(rel))
        log["notes"].append("保真复制 %s（不改名、不改内容）" % cp)

    # ---------- 3c) 显式附加文件（src 相对仓库根，dst 相对包根） ----------
    # 用途：源包缺少 Golden 模板需要的资源时（例如 PATH_OVERRIDE_ONLY 类型
    # 系统性没有 body chain，而 f_wst 模板强制引用 JRwst*.chain），
    # 用**声明式**方式补一个明确来源的文件，而不是让 PFB 出现悬空引用。
    for e in spec.get("extra_files", []):
        s = Path(e["src"])
        if not s.exists():
            raise SystemExit("STOP：extra_files 源不存在 %s" % s)
        dst = out / e["dst"]
        write(dst, s.read_bytes())
        log["added"].append(e["dst"])
        log["notes"].append("显式附加 %s ← %s（用途：%s）"
                            % (e["dst"], e["src"], e.get("purpose", "未声明")))

    if spec.get("prefab"):
        pf = spec["prefab"]
        pdir = Path(pf["template_dir"])
        rawd = rep / "_pfb_raw"
        if rawd.exists():
            shutil.rmtree(rawd)
        r = pfb_rewrite(
            in_dir=str(pdir),
            out_dir=str(rawd),
            pairs=[tuple(x) for x in pf["rewrite"]] or [],
            filename_pairs=[tuple(x) for x in pf.get("filename_rewrite", [])] or [],
            report_dir=str(rep),
        )
        base = out_natives / "player" / "prefab" / "mod" / "f" / ("pl%s" % spec["slot"])
        base.mkdir(parents=True, exist_ok=True)
        for f in sorted(rawd.glob("*.pfb.17")):
            write(base / f.name, f.read_bytes())
            log["added"].append("natives/STM/player/prefab/mod/f/pl%s/%s" % (spec["slot"], f.name))
        log["pfb_rewrite"] = r if isinstance(r, dict) else str(r)
        if rawd.exists():
            shutil.rmtree(rawd)

    # ---------- 4b) 产物 mesh 版本复检（TODO 08 的真实语义：登记的是"本包携带"） ----------
    # 只抽部分资源构建时（如盟友包只取 NPC 部分），源里那些不携带的文件不应强制登记。
    carried = {}
    for _p in sorted(out.rglob("*")):
        if not _p.is_file() or ".mesh." not in _p.name:
            continue
        _b = _p.read_bytes()
        if _b[:4] != b"MESH":
            carried.setdefault("NOT_MESH", []).append(_p.name)
            continue
        carried.setdefault("0x%08X" % struct.unpack_from("<I", _b, 4)[0], []).append(_p.name)
    log["carried_mesh_versions"] = {k: sorted(v) for k, v in carried.items()}
    _unreg = sorted(k for k in carried if k != "NOT_MESH" and int(k, 0) not in registered)
    if _unreg:
        raise SystemExit(
            "STOP：产物将携带未登记的 MESH 版本 %s（只复制不解析）。"
            "按 TODO 08，随包携带的新版本也必须显式登记：写进 spec.register_mesh_version"
            % ", ".join(_unreg))
    _carried_extra = sorted(k for k in carried
                            if k != "NOT_MESH" and int(k, 0) not in parse_versions)
    if _carried_extra:
        log["notes"].append("以下版本仅**逐字节复制、不解析**，已在 spec 登记，不构成生产支持：%s"
                            % ", ".join(_carried_extra))

    # ---------- 5) LuaBone：按 spec 的 lua_bone_from 生成 ----------
    shadow = Path("base/f_shadow.json")
    # 缺失骨放行（研究用途）：只放行 spec **逐骨显式声明**的骨，不是全局开关。
    # 生产门禁保持原样 —— 未声明就缺失，仍然 STOP。
    allow_missing = set(spec.get("lua_bone_allow_missing") or [])
    for rename, mesh in sorted(lua_bone_src.items()):
        try:
            result, gen = luabone_generate(str(mesh), str(shadow), allowed_versions=allowed,
                                           allow_missing_target=bool(allow_missing))
        except ManualReviewRequired as exc:
            raise SystemExit(
                "STOP：LuaBone 关键骨缺失，且未在 spec.lua_bone_allow_missing 中声明放行 —— %s" % exc)
        missing = set(gen.get("missing_target_bones") or [])
        undeclared = missing - allow_missing
        if undeclared:
            raise SystemExit(
                "STOP：本包缺失 %s，其中 %s 未在 spec.lua_bone_allow_missing 声明；"
                "只允许逐骨放行，不做全局放宽" % (sorted(missing), sorted(undeclared)))
        dst = out / "reframework" / "data" / "LUABoneSystem" / "custom" / ("%s.json" % rename)
        luabone_dump(result, str(dst))
        log["lua_bone"][rename] = {
            "from_mesh": str(mesh), "mesh_version": gen["mesh_version"],
            "matched": gen["matched_count"], "aliases": len(gen["aliases_used"]),
            "missing_target": gen["missing_target_bones"],
            "missing_target_allowed_by_spec": sorted(allow_missing),
            "missing_target_released_for_research": bool(missing),
            "output_key_count": gen["output_key_count"],
            "max_abs_offset": gen["max_abs_offset"],
            "missing_policy": MISSING_POLICY,
        }
        if missing:
            log["notes"].append(
                "研究用途：按 spec.lua_bone_allow_missing 放行了缺失骨 %s（生产门禁未放宽）"
                % sorted(missing))
        log["added"].append(str(dst.relative_to(out)))
        write(rep / ("luabone-report-%s.json" % rename),
              json.dumps(gen, indent=2, ensure_ascii=False) + "\n")
        # Golden / J018 的既有约定：私有资源名逐个配一份 JSON，dummy 槽的那几份内容相同。
        # 为保持"相对既有基线单变量"，此处按 spec 声明的名字镜像同一份内容。
        for alias in spec.get("lua_bone_mirror", {}).get(rename, []):
            adst = out / "reframework" / "data" / "LUABoneSystem" / "custom" / ("%s.json" % alias)
            luabone_dump(result, str(adst))
            log["added"].append(str(adst.relative_to(out)))
            log["notes"].append("LuaBone %s 镜像 %s 的内容（保持既有约定）" % (alias, rename))

    # ---------- 6) modinfo ----------
    write(out / "modinfo.ini", spec.get("modinfo") or (
        "name=%s\nversion=%s\nauthor=dddder4 / Rebuild\n"
        "description=NPC->Player taxonomy runtime validation test %s. %s\n"
        % (spec["modinfo_name"], spec.get("version", "test1"), spec["label"],
           spec.get("modinfo_description", ""))))

    # ---------- 7) 构建后引用闭合自检（硬门禁） ----------
    # 槽绑定由 spec 声明，而 PFB 模板固定引用 mesh/mdf2/chain 三件套：
    # carrier 少一个 .chain 时模板照样引用它 —— 包能建出来、能打包、能安装，
    # 直到装备加载才表现为"卡住无法动弹"。所以自检必须落在构建期。
    refs = check_package(out, slot=spec.get("slot"))
    log["refs_selfcheck"] = {"verdict": refs["verdict"], "findings": refs["findings"]}
    write(rep / "refs-selfcheck.json", json.dumps(refs, indent=2, ensure_ascii=False) + "\n")

    write(rep / "build-log.json", json.dumps(log, indent=2, ensure_ascii=False) + "\n")
    print("== build %s ==" % spec["label"])
    print("  asset=%s slot=%s  private=%s  pfb=%s" % (
        spec["asset_id"], spec.get("slot"), bool(private), bool(spec.get("prefab"))))
    print("  新增文件 %d" % len(log["added"]))
    for n in log["notes"]:
        print("   - %s" % n)
    print("  引用闭合自检：%s" % refs["verdict"])
    for f in refs["findings"]:
        print("   !! [%s] %s -> %s" % (f["kind"], f["where"], f["detail"]))
    if refs["verdict"] != "PASS":
        raise SystemExit("STOP：构建产物引用不闭合 —— PFB 引用的资源在包内不存在实体")
    return 0


JSON_DUMMY_DIR = Path("base/golden/J017_AstonMachan_R1/mod/natives/STM/player/JRRB/J017")

if __name__ == "__main__":
    raise SystemExit(main())

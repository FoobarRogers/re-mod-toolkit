#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""包内引用完整性检查 —— 换装备 id 后 / 打包后的通用静态验证。

`reslot_package.py` 证明的是"**只改了路径**"；本工具证明改完之后
"**引用仍然闭合**"。两者合起来才是换 id 的完整验证链。

检查项：

  1. **PFB → 资源实体**：PFB 的 `path_table` 里每条 `player/...` 路径，
     包内必须存在 `natives/STM/<path>.<版本后缀>`；
  2. **PFB → 对象名**：`game_object_name_candidates` 必须能在包内找到同名部件
     （`<name>.<任意后缀>` 或 `<name>/` 下至少一个文件）；
  3. **LuaBone custom JSON ↔ 部件名**：LuaBoneSystem 按**部件对象名**加载
     `custom/<part>.json`，而部件名来自 mesh 文件名。
     所以 `custom/f_helm312.json` 要求包内存在部件 `f_helm312`
     （改名时 mesh 与 JSON 必须同步 —— 这是换 id 最容易漏的一处）；
  4. **装备 id 一致性**：包内 player 侧出现的 `plNNN` / `<stem>NNN` 是否只有声明的那个；
  5. **引擎内置引用白名单**：`systems/rendering/NullWhite.tex` 这类不需要包内实体。

结果只有 `PASS` / `FAIL`。只读，不修改任何东西。
"""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from inspect_npc_pfb import parse_pfb  # noqa: E402

# 引擎内置、不随 mod 分发的引用（前轮已确认 + 本轮实测补充）
BUILTIN_PREFIXES = (
    "systems/rendering/",      # NullWhite.tex 等
    "Sound/Asset/",            # 装备音效容器（.wcc）：源 PFB 固有构成，游戏内置
)
BUILTIN_NAMES = {"NullWhite.tex"}

# 装备侧 PFB 的已知版本族：装备侧 f_* = v1，v7 为 NPC prefab
PFB_ALLOWED_DEFAULT = (7, 1)


def _natives(name):
    """把 zip 内成员名规范成 natives/STM/ 之后的相对路径。"""
    n = name.replace("\\", "/")
    for p in ("natives/STM/", "natives/stm/"):
        if n.startswith(p):
            return n[len(p):]
    return None


@contextlib.contextmanager
def _members(package):
    """统一读取 zip 与已解包目录。

    构建器需要在**打包之前**就用同一套规则自检产物，否则少一个 `.chain`
    要等到换 id / 实机才发现（本工具最初只吃 zip，正是那次的漏洞来源）。
    """
    p = Path(package)
    if p.is_dir():
        names = [str(f.relative_to(p)).replace("\\", "/")
                 for f in sorted(p.rglob("*")) if f.is_file()]
        yield names, lambda n: (p / n).read_bytes()
    else:
        with zipfile.ZipFile(p) as z:
            yield z.namelist(), z.read

def check_package(package, slot=None, allowed_pfb_versions=PFB_ALLOWED_DEFAULT):
    findings = []
    with _members(package) as (members, read):
        rel = {}
        for m in members:
            r = _natives(m)
            if r:
                rel[r] = m

        def exists_ref(path):
            """PFB 引用（无版本后缀）→ 包内是否有实体。"""
            for r in rel:
                if r == path or r.startswith(path + "."):
                    return True
            return False

        # 部件名集合：natives 下每个文件的 stem（去最后一个点后缀）
        part_names = set()
        for r in rel:
            base = r.split("/")[-1]
            if "." in base:
                part_names.add(base.split(".")[0])
            else:
                part_names.add(base)

        # 1 + 2：PFB 引用
        for m in members:
            if ".pfb." not in m:
                continue
            try:
                rep = parse_pfb(read(m), source=m, allowed_versions=tuple(allowed_pfb_versions))
            except Exception as exc:                                  # noqa: BLE001
                findings.append(("PFB_PARSE_FAIL", m, str(exc)))
                continue
            for e in rep.get("path_table", []):
                p = e.get("path") or ""
                if not p or p.startswith(BUILTIN_PREFIXES) or p.split("/")[-1] in BUILTIN_NAMES:
                    continue
                if not exists_ref(p):
                    findings.append(("PFB_DANGLING_REF", m, p))
            for c in rep.get("game_object_name_candidates", []):
                n = c.get("name")
                if n and n not in part_names:
                    findings.append(("PFB_OBJECT_MISSING", m, n))
            for e in rep.get("section2_ref_table", []):
                p = e.get("path")
                if p and not p.startswith(BUILTIN_PREFIXES) and not exists_ref(p):
                    findings.append(("PFB_DANGLING_REF_S2", m, p))

        # 3：LuaBone JSON ↔ 部件名
        lua = [m for m in members if "/LUABoneSystem/custom/" in m.replace("\\", "/")]
        for m in lua:
            stem = m.replace("\\", "/").split("/")[-1]
            if not stem.endswith(".json"):
                continue
            part = stem[:-5]
            if part not in part_names:
                findings.append(("LUABONE_ORPHAN", m,
                                 "包内没有名为 %s 的部件；LuaBone 按部件对象名加载，永远不会命中" % part))

        # 4：装备 id 一致性
        pl_ids = set()
        for r in rel:
            for mm in re.finditer(r"(?:^|/)pl(\d{3,4})(?:/|$)", r):
                pl_ids.add(mm.group(1))
            for mm in re.finditer(r"(?:^|/)f_[a-z]+(\d{3,4})\.", r):
                pl_ids.add(mm.group(1))
        if slot and pl_ids and set([str(slot)]) != pl_ids:
            findings.append(("SLOT_MISMATCH", Path(package).name,
                             "包内出现装备 id %s，声明的是 %s" % (sorted(pl_ids), slot)))

    return {"package": str(package), "slot": str(slot) if slot else None,
            "member_count": len(members), "pfb_count": sum(1 for m in members if ".pfb." in m),
            "luabone_count": len(lua), "equipment_ids": sorted(pl_ids),
            "findings": [{"kind": k, "where": w, "detail": d} for k, w, d in findings],
            "verdict": "PASS" if not findings else "FAIL"}


def main(argv=None):
    ap = argparse.ArgumentParser(description="包内引用完整性检查（换 id 后 / 打包后）")
    ap.add_argument("zips", nargs="+")
    ap.add_argument("--slot", help="声明该包应使用的装备 id（可选）")
    ap.add_argument("--baseline", action="append", default=[],
                    help="源包（可重复）。在源包里同样出现的问题会标为 INHERITED，不计入 FAIL")
    ap.add_argument("--json", help="把结果写成 JSON")
    args = ap.parse_args(argv)

    # 源包已有的问题签名 —— 用来区分"我们引入的"与"继承的"
    inherited = set()
    for b in args.baseline:
        for f in check_package(b, None)["findings"]:
            inherited.add((f["kind"], f["detail"]))

    results = []
    for z in args.zips:
        r = check_package(z, args.slot)
        new_findings = []
        for f in r["findings"]:
            if (f["kind"], f["detail"]) in inherited:
                f = dict(f, inherited_from_source=True)
            new_findings.append(f)
        r["findings"] = new_findings
        r["own_findings"] = [f for f in new_findings if not f.get("inherited_from_source")]
        r["inherited_findings"] = [f for f in new_findings if f.get("inherited_from_source")]
        r["verdict"] = "PASS" if not r["own_findings"] else "FAIL"
        results.append(r)

    for r in results:
        print("%-6s %s" % (r["verdict"], Path(r["package"]).name))
        print("       成员 %d / PFB %d / LuaBone %d / 包内装备 id %s"
              % (r["member_count"], r["pfb_count"], r["luabone_count"], r["equipment_ids"]))
        for f in r["own_findings"]:
            print("       !! [%s] %s -> %s" % (f["kind"], f["where"], f["detail"]))
        for f in r["inherited_findings"]:
            print("       (继承源包) [%s] %s -> %s" % (f["kind"], f["where"], f["detail"]))

    if args.json:
        p = Path(args.json)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8", newline="\n")
    return 0 if all(r["verdict"] == "PASS" for r in results) else 2


if __name__ == "__main__":
    sys.exit(main())

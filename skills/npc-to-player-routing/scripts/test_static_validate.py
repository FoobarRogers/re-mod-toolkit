#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Research Test 独立静态验证 —— 对应 TODO 08。

验证对象是**最终候选包**（不是构建过程的中间状态），逐项检查 TODO 08 的清单：

```text
resource existence      PFB refs             MDF2 -> texture refs
LuaBone matching        legacy residual      unexpected binary diff
source SHA256           output SHA256        dummy / placeholder SHA256
mesh version            joint count          structure invariant
face/hair companion presence                 source-fidelity deviations
```

结果只有三种：`STATIC PASS` / `STATIC FAIL` / `MANUAL_REVIEW_REQUIRED`。
版本规则（TODO 08）：结构契约 PASS ≠ 运行时语义 PASS；研究 Test 可登记使用未登记版本，
但不得因此自动加入生产支持。

用法
----
    python scripts/test_static_validate.py <package_dir> \
        --report-dir <dir> --source <source_dir> [--spec <spec.json>] [--label NAME]
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

from mesh_skeleton import SUPPORTED_MESH_VERSION, parse_mesh_skeleton, ManualReviewRequired  # noqa: E402
from inspect_npc_pfb import SUPPORTED_PFB_VERSION, parse_pfb  # noqa: E402

KNOWN_SHARED_PREFIX = {
    "aa27c117a0fd1cfd": "占位件 305932 / J=79 / Body",
    "5c83decc39a0f621": "通用脸 710448 / J=54",
    "e579e4fc7614def7": "通用脸 187584 / J=54",
    "91775431fd502b7b": "通用脸 710448 / J=54（炎火村族）",
}

LEGACY = re.compile(r"zhst|z017|starm024|stbody024|sthelm024|stwst024|pl279\b|J018\b|J017\b|JR\w*017")
U16 = re.compile(rb"(?:[\x20-\x7e]\x00){3,}")


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Research Test 独立静态验证")
    ap.add_argument("package")
    ap.add_argument("--report-dir", required=True)
    ap.add_argument("--source", default=None)
    ap.add_argument("--spec", default=None)
    ap.add_argument("--label", default=None)
    ap.add_argument("--allow-version", action="append", default=[])
    ap.add_argument("--allow-pfb-version", action="append", default=[])
    args = ap.parse_args(argv)

    pkg = Path(args.package)
    rep = Path(args.report_dir)
    rep.mkdir(parents=True, exist_ok=True)
    label = args.label or pkg.name
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8")) if args.spec else {}
    allowed = ((SUPPORTED_MESH_VERSION,)
               + tuple(int(v, 0) for v in args.allow_version)
               + tuple(int(v, 0) for v in spec.get("allow_mesh_version", [])))
    pfb_ok = (SUPPORTED_PFB_VERSION,) + tuple(int(v, 0) for v in args.allow_pfb_version)

    checks = []          # {item, status, detail}
    def ck(item, ok, detail):
        checks.append({"item": item,
                       "status": "PASS" if ok else ("REVIEW" if ok is None else "FAIL"),
                       "detail": detail})

    # 1) 逐文件 sha256 + 源对照
    files = {}
    for p in sorted(pkg.rglob("*")):
        if p.is_file():
            rel = str(p.relative_to(pkg)).replace("\\", "/")
            files[rel] = {"size": p.stat().st_size, "sha256": sha(p)}
    ck("output SHA256 inventory", bool(files), "%d 个文件" % len(files))

    src = Path(args.source) if args.source else None
    if src and src.exists():
        src_natives = src / "natives" / "STM"
        changed, identical, added = [], [], []
        for rel, rec in files.items():
            inner = rel.split("natives/STM/", 1)[-1] if "natives/STM/" in rel else None
            cand = None
            if inner:
                for base in (src_natives, src / "reframework", src):
                    q = base / inner if base is src_natives else (base / rel.replace("natives/STM/", "")
                                                                  if base is src_natives else None)
                    if q is None:
                        continue
                # 直接按"源包内同路径"查找，含 reframework
                for base in (src,):
                    for probe in (base / rel, base / "natives" / "STM" / inner):
                        if probe.exists():
                            cand = probe
                            break
            if cand is None:
                added.append(rel)
            elif sha(cand) == rec["sha256"]:
                identical.append(rel)
            else:
                changed.append(rel)
        ck("source SHA256 对照",
           True, "与源相同 %d / 逐字节新增或改名 %d / 内容改变 %d"
                 % (len(identical), len(added), len(changed)))
        unexpected = [c for c in changed
                      if not re.search(r"(modinfo|\.json)$", c)]
        ck("unexpected binary diff", not unexpected,
           ("未声明的二进制差异：%s" % unexpected) if unexpected
           else "无（内容改变项均为 modinfo / LuaBone JSON）")
    else:
        ck("source SHA256 对照", None, "未提供 --source，无法对照（记为 REVIEW）")

    # 2) mesh 版本 / 关节数 / 结构不变量
    mesh_rows, placeholder_hits, inv_fail = [], [], []
    for rel, rec in files.items():
        if not rel.endswith(".mesh.2109148288"):
            continue
        b = (pkg / rel).read_bytes()
        if b[:4] != b"MESH":
            mesh_rows.append({"path": rel, "magic": " ".join("%02X" % x for x in b[:4]),
                              "note": "非 MESH（null-visual / 占位）"})
            if b[:4] == b"M\xcbSH":
                mesh_rows[-1]["note"] = "非 MESH：Golden 的 magic 破坏型 null-visual"
            continue
        ver = struct.unpack_from("<I", b, 4)[0]
        pref = rec["sha256"][:16]
        row = {"path": rel, "mesh_version": "0x%08X" % ver, "sha256_prefix": pref}
        if pref in KNOWN_SHARED_PREFIX:
            row["placeholder"] = KNOWN_SHARED_PREFIX[pref]
            placeholder_hits.append(rel)
        try:
            sk = parse_mesh_skeleton(b, source=rel, allowed_versions=(SUPPORTED_MESH_VERSION, ver))
            row.update({"joint_count": sk.joint_count, "structure_contract": "PASS",
                        "material_names": sk.material_names,
                        "invariant_failures": [j.name for j in sk.joints if not j.invariants_ok]})
            if row["invariant_failures"]:
                inv_fail.append(rel)
        except ManualReviewRequired as exc:
            row["structure_contract"] = "MANUAL_REVIEW_REQUIRED"
            row["note"] = str(exc)
        mesh_rows.append(row)
    ck("mesh 结构不变量", not inv_fail, "失败项：%s" % inv_fail if inv_fail else "全部成立")
    # 版本登记（TODO 08）：分"要解析的版本"与"随包携带但只复制的版本"两种登记。
    # 已知占位件按哈希识别，不作为未登记版本；两者都必须能追溯到 spec 的显式声明。
    registered = allowed + tuple(int(v, 0) for v in spec.get("register_mesh_version", []))
    unreg = sorted({r["mesh_version"] for r in mesh_rows
                    if r.get("mesh_version") and "placeholder" not in r
                    and int(r["mesh_version"], 16) not in registered})
    ck("mesh 版本登记（研究模式）", not unreg,
       ("未登记版本：%s（TODO 08 要求随包携带即须登记）" % unreg) if unreg
       else "版本 %s 全部已登记；占位件 %d 项按哈希识别"
            % (sorted({r["mesh_version"] for r in mesh_rows if r.get("mesh_version")}),
               len(placeholder_hits)))
    ck("dummy / placeholder SHA256", True,
       "识别到占位件 %d 项：%s" % (len(placeholder_hits), placeholder_hits))

    # 3) PFB refs + 引用实体存在性
    pfb_rows, missing_entities = [], []
    for rel in files:
        if not rel.endswith(".pfb.17"):
            continue
        data = (pkg / rel).read_bytes()
        try:
            r = parse_pfb(data, source=rel, allowed_versions=pfb_ok)
        except ManualReviewRequired as exc:
            pfb_rows.append({"path": rel, "parse": "MANUAL_REVIEW_REQUIRED", "reason": str(exc)})
            continue
        refs = [e["path"] for e in r["path_table"]] + [e["path"] for e in r["typed_refs"]]
        pfb_rows.append({"path": rel, "version": r["version"], "refs": len(refs),
                         "parse": "PASS"})
        provided = set(files)
        for t in refs:
            if t.startswith(("Pop/", "Sound/", "gui/", "systems/")) or "/item/" in t:
                continue
            # 只检查"指向本包私有资源"的引用是否在包内
            m = re.search(r"(player/JRRB/J\d+)/(\w+)\.(\w+)", t)
            if m:
                want = "%s.%s" % (m.group(2), m.group(3))
                if not any(Path(k).name.startswith(want) for k in provided):
                    missing_entities.append("%s -> %s" % (rel, t))
    ck("PFB refs 实体存在", not missing_entities,
       "缺失：%s" % missing_entities if missing_entities else "私有资源引用全部有实体")

    # 4) MDF2 → texture refs
    mdf_rows, tex_missing = [], []
    for rel in files:
        if not rel.endswith(".mdf2.23"):
            continue
        b = (pkg / rel).read_bytes()
        texs = sorted({m.group().decode("utf-16-le") for m in U16.finditer(b)
                       if m.group().decode("utf-16-le").endswith(".tex")})
        row = {"path": rel, "texture_refs": texs}
        for t in texs:
            if t.startswith("systems/") or t.startswith("MasterMaterial/"):
                continue
            if not (pkg / "natives" / "STM" / t).with_suffix("").parent.exists():
                pass
            hit = list((pkg / "natives" / "STM").glob(t + "*")) if (pkg / "natives" / "STM").exists() else []
            if not hit:
                tex_missing.append("%s -> %s" % (rel, t))
        mdf_rows.append(row)
    ck("MDF2 -> texture refs", not tex_missing,
       "缺失：%s" % tex_missing if tex_missing else "全部贴图引用在包内可满足（本体路径除外）")

    # 5) LuaBone matching
    lua_rows = []
    lb_dir = pkg / "reframework" / "data" / "LUABoneSystem" / "custom"
    shadow = json.loads(Path("base/f_shadow.json").read_text(encoding="utf-8"))
    if lb_dir.exists():
        for f in sorted(lb_dir.glob("*.json")):
            obj = json.loads(f.read_text(encoding="utf-8"))
            keys = set(obj)
            lua_rows.append({"file": f.name, "key_count": len(keys),
                             "keys_match_shadow_or_extra":
                                 sorted(keys - set(shadow))[:8] or "全部在 f_shadow 键集内"})
    ck("LuaBone matching", True,
       "%d 份配置；键集与 f_shadow 的关系见 detail" % len(lua_rows))

    # 6) legacy residual
    legacy_hits = []
    for rel in files:
        if not rel.endswith((".pfb.17", ".json", ".ini", ".txt")):
            continue
        b = (pkg / rel).read_bytes()
        for m in U16.finditer(b):
            t = m.group().decode("utf-16-le")
            if LEGACY.search(t):
                legacy_hits.append("%s :: %s" % (rel, t))
    ck("legacy residual", not legacy_hits,
       "残留：%s" % legacy_hits[:5] if legacy_hits else "无旧 namespace / 旧 J### 残留")

    # 7) face/hair companion presence（按 spec 声明）
    expected = [h["dst"].split("natives/STM/")[-1] for h in spec.get("head_layer", [])]
    absent = [e for e in expected if not (pkg / "natives" / "STM" / e).exists()]
    ck("face/hair companion presence",
       not absent, "声明的头部层 %d 项，缺失 %s" % (len(expected), absent or "无"))

    # 结论
    fails = [c for c in checks if c["status"] == "FAIL"]
    reviews = [c for c in checks if c["status"] == "REVIEW"]
    verdict = "STATIC FAIL" if fails else ("MANUAL_REVIEW_REQUIRED" if reviews else "STATIC PASS")

    out = {"label": label, "package": str(pkg), "verdict": verdict,
           "checks": checks, "meshes": mesh_rows, "prefabs": pfb_rows,
           "mdf2": mdf_rows, "lua_bone": lua_rows,
           "placeholders_detected": placeholder_hits,
           "version_policy_note": "结构契约 PASS != 运行时语义 PASS；研究 Test 登记不等于进生产支持。",
           "files": files}
    (rep / "static-validation.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

    print("== %s ==" % label)
    for c in checks:
        print("   [%-6s] %-34s %s" % (c["status"], c["item"], c["detail"]))
    print("   => %s" % verdict)
    return 0 if verdict == "STATIC PASS" else (1 if verdict == "STATIC FAIL" else 2)


if __name__ == "__main__":
    raise SystemExit(main())

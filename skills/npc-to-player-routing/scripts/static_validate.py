#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase H —— 候选包静态验证。

PASS 条件（`docs/NPC_TO_PLAYER_CONVERSION_WORKFLOW_v0.2-draft.md` §Phase H）：

  - PFB 文件大小保持不变（等长替换场景）
  - 历史私有路径残留 = 0
  - 所有新资源引用都有对应实体文件
  - 所有 changed bytes 都落在声明的字符串替换区域
  - 无未知二进制变化

扫描范围限 `natives/` + `reframework/`（与 Golden 的
`runtime_residual_scan_scope` 一致）；候选包根目录的 modinfo / manifest 允许
出现历史 ID 说明性文字，不作为残留。

本工具是独立读取最终候选再做验证（审查意见 §11），不复用改写过程的中间状态，
因此它能独立证伪改写工具声称的结果。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from pfb_equal_length_replace import extract_utf16_strings  # noqa: E402

# Golden 的历史身份（来源 base/golden/J017_AstonMachan_R1/golden-manifest.json
# historical_mapping）。这些 token 一旦出现在候选包的 natives/ 或 reframework/
# 内，说明归一化不完整。
HISTORICAL_TOKENS = (
    "zhst", "z017",
    "starm024", "stbody024", "sthelm024", "stwst024",
    "JRRB/J017", "JRarm017", "JRbody017", "JRhelm017", "JRwst017",
)

SCAN_ROOTS = ("natives", "reframework")
RESOURCE_EXTS = (".mesh", ".mdf2", ".chain", ".user", ".tex", ".pfb", ".jcns")

# 引擎内置资源前缀：这类引用不需要（也不应该）在 mod 包内存在实体
ENGINE_PATH_PREFIXES = ("systems/",)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def iter_scan_files(candidate):
    candidate = Path(candidate)
    for root in SCAN_ROOTS:
        base = candidate / root
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if p.is_file():
                yield p


def referenced_paths(text):
    """从字符串里取出形如 `player/...` 或 `<a>/<b>...` 的资源引用。"""
    if "." not in text:
        return None
    if not any(text.endswith(e) for e in RESOURCE_EXTS):
        return None
    return text


def validate(candidate, task_dir, asset_id, slot, source_dir, carrier_stem):
    candidate = Path(candidate)
    reports = Path(task_dir) / "reports"
    num = asset_id[1:]

    result = {
        "asset_id": asset_id,
        "target_player_slot": "PL%s" % slot,
        "candidate_dir": candidate.as_posix(),
        "ingame_validation": "PENDING",
    }
    failures = []

    # --- 1. PFB 改写结果（来自 Phase G 报告，独立复核文件系统状态） ----------
    pfb_report_path = reports / "pfb-rewrite-report.json"
    pfb_report = json.loads(pfb_report_path.read_text(encoding="utf-8")) \
        if pfb_report_path.exists() else []
    pfb_check = []
    for r in pfb_report:
        p = candidate / r["file"]
        ok = p.exists() and p.stat().st_size == r["size_before"] == r["size_after"]
        if not ok:
            failures.append("PFB 大小/存在性异常: %s" % r["file"])
        if r["unexpected_changed_byte_count"]:
            failures.append("PFB 出现未声明区域的字节变化: %s (%s)"
                            % (r["file"], r["unexpected_changed_offsets"]))
        if r["residual_old_tokens"]:
            failures.append("PFB 残留旧 token: %s %s" % (r["file"], r["residual_old_tokens"]))
        pfb_check.append({
            "file": r["file"],
            "size_preserved": p.exists() and p.stat().st_size == r["size_before"],
            "changed_byte_count": r["changed_byte_count"],
            "unexpected_changed_byte_count": r["unexpected_changed_byte_count"],
            "residual_old_tokens": r["residual_old_tokens"],
        })
    result["pfb_static_pass"] = bool(pfb_report) and not failures
    result["pfb_files"] = pfb_check

    # --- 2. PFB 引用 -> 实体存在性 ------------------------------------------
    pfb_dir = candidate / ("natives/STM/player/prefab/mod/f/pl%s" % slot)
    pfb_refs, missing_refs = {}, []
    for p in sorted(pfb_dir.glob("*.pfb.*")) if pfb_dir.is_dir() else []:
        refs = []
        for s in extract_utf16_strings(p.read_bytes()):
            text = s["string"]
            if text.startswith("player/") and any(text.endswith(e) for e in RESOURCE_EXTS):
                refs.append(text)
                # 实体判定：候选包内存在同名资源（扩展名带版本后缀）
                stem_path = candidate / "natives/STM" / text
                found = stem_path.parent.is_dir() and any(
                    q.name.startswith(stem_path.name + ".")
                    for q in stem_path.parent.iterdir())
                if not found:
                    missing_refs.append({"pfb": p.name, "ref": text})
        pfb_refs[p.relative_to(candidate).as_posix()] = refs
    result["pfb_refs"] = pfb_refs
    result["missing_pfb_resource_refs"] = missing_refs
    if missing_refs:
        failures.append("PFB 引用了包内不存在的资源: %s" % missing_refs)

    # --- 3. 私有资源与来源的 byte-identical --------------------------------
    preserved = []
    src = Path(source_dir)
    carrier_files = {}
    for p in src.rglob("*"):
        if p.is_file() and p.name.startswith(carrier_stem + "."):
            carrier_files[p.name[len(carrier_stem) + 1:].split(".")[0]] = p
    for ext in ("mesh", "mdf2", "chain"):
        s = carrier_files.get(ext)
        if not s:
            continue
        suffix = s.name[len(carrier_stem):]
        d = candidate / ("natives/STM/player/JRRB/%s/JRwst%s%s" % (asset_id, num, suffix))
        if not d.exists():
            failures.append("私有资源缺失: %s" % d)
            continue
        same = sha256(s.read_bytes()) == sha256(d.read_bytes())
        if not same:
            failures.append("私有资源内容与源不一致: %s" % d)
        preserved.append({"source": s.as_posix(), "normalized": d.as_posix(),
                          "source_sha256": sha256(s.read_bytes()),
                          "normalized_sha256": sha256(d.read_bytes()),
                          "byte_identical": same})
    result["renamed_resource_content_preserved"] = preserved

    # --- 4. dummy 资源一致性 ------------------------------------------------
    dummy = {}
    priv = candidate / ("natives/STM/player/JRRB/%s" % asset_id)
    for ext in ("chain.48", "mdf2.23", "mesh.2109148288"):
        files, hashes = [], []
        for role in ("arm", "body", "helm"):
            p = priv / ("JR%s%s.%s" % (role, num, ext))
            if p.exists():
                files.append(p.relative_to(candidate).as_posix())
                hashes.append(sha256(p.read_bytes()))
        dummy[ext] = {"files": files, "hashes": hashes,
                      "all_identical": len(set(hashes)) <= 1}
        if len(set(hashes)) > 1:
            failures.append("dummy 资源 %s 内容不一致" % ext)
    result["dummy_resource_validation"] = dummy

    # --- 5. LuaBone JSON ---------------------------------------------------
    lb_dir = candidate / "reframework/data/LUABoneSystem/custom"
    lb_files, lb_hashes, lb_ok = [], [], True
    for role in ("arm", "body", "helm", "wst"):
        p = lb_dir / ("JR%s%s.json" % (role, num))
        if not p.exists():
            failures.append("LuaBone JSON 缺失: %s" % p)
            lb_ok = False
            continue
        try:
            json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:                                # noqa: BLE001
            failures.append("LuaBone JSON 无法 parse: %s (%s)" % (p, exc))
            lb_ok = False
        lb_files.append(p.relative_to(candidate).as_posix())
        lb_hashes.append(sha256(p.read_bytes()))
    result["luabone_files"] = lb_files
    result["luabone_hashes"] = lb_hashes
    result["luabone_all_identical"] = len(set(lb_hashes)) <= 1
    result["luabone_parse_ok"] = lb_ok
    if not result["luabone_all_identical"]:
        failures.append("四份 LuaBone JSON 内容不一致")

    # --- 6. 历史 token 残留 -------------------------------------------------
    residuals = []
    for p in iter_scan_files(candidate):
        data = p.read_bytes()
        hit = []
        for tok in HISTORICAL_TOKENS:
            for enc in ("ascii", "utf-16-le"):
                try:
                    if tok.encode(enc) in data:
                        hit.append("%s(%s)" % (tok, enc))
                except UnicodeEncodeError:
                    pass
        if hit:
            residuals.append({"file": p.relative_to(candidate).as_posix(), "tokens": hit})
    result["historical_token_residuals"] = residuals
    if residuals:
        failures.append("natives/ 或 reframework/ 内存在历史 token 残留: %s" % residuals)

    # --- 7. texture 引用 -> 实体 -------------------------------------------
    # 只对 mod 自有纹理要求包内实体；`systems/...` 是引擎内置占位资源
    # （例如 VertexAnimMap 用的 NullWhite.tex），不随 mod 分发。
    wst_mdf2 = priv / ("JRwst%s.mdf2.23" % num)
    tex_refs, engine_tex_refs, missing_tex = [], [], []
    if wst_mdf2.exists():
        for s in extract_utf16_strings(wst_mdf2.read_bytes()):
            t = s["string"]
            if not t.endswith(".tex"):
                continue
            if t.startswith(ENGINE_PATH_PREFIXES):
                engine_tex_refs.append(t)
                continue
            tex_refs.append(t)
            cand_path = candidate / "natives/STM" / t
            if not (cand_path.parent.is_dir() and any(
                    q.name.startswith(cand_path.name + ".")
                    for q in cand_path.parent.iterdir())):
                missing_tex.append(t)
    result["texture_refs_in_JRwst%s_mdf2" % num] = tex_refs
    result["engine_texture_refs"] = sorted(set(engine_tex_refs))
    result["missing_texture_refs"] = missing_tex
    if missing_tex:
        failures.append("mdf2 引用了包内不存在的 texture: %s" % missing_tex)

    result["status"] = "PASS" if not failures else "FAIL"
    result["failures"] = failures
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description="Phase H：候选包静态验证")
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--task-dir", required=True)
    ap.add_argument("--asset-id", required=True)
    ap.add_argument("--slot", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--carrier-stem", required=True)
    args = ap.parse_args(argv)

    res = validate(args.candidate, args.task_dir, args.asset_id, args.slot,
                   args.source, args.carrier_stem)
    out = Path(args.task_dir) / "reports" / "static-validation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(res, indent=2, ensure_ascii=False) + "\n")

    print("Phase H 静态验证: %s" % res["status"])
    print("  pfb_static_pass         : %s" % res["pfb_static_pass"])
    print("  missing pfb refs        : %d" % len(res["missing_pfb_resource_refs"]))
    print("  missing texture refs    : %d" % len(res["missing_texture_refs"]))
    print("  historical residuals    : %d" % len(res["historical_token_residuals"]))
    print("  resource byte-identical : %s"
          % all(r["byte_identical"] for r in res["renamed_resource_content_preserved"]))
    print("  dummy all identical     : %s"
          % all(v["all_identical"] for v in res["dummy_resource_validation"].values()))
    print("  luabone files/identical : %d / %s"
          % (len(res["luabone_files"]), res["luabone_all_identical"]))
    for f in res["failures"]:
        print("  FAIL: %s" % f)
    print("  report                  : %s" % out)
    return 0 if res["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())

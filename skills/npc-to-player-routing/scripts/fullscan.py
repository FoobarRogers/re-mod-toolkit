#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase I —— 候选包全包扫描。

检查项（`docs/NPC_TO_PLAYER_CONVERSION_WORKFLOW_v0.2-draft.md` §Phase I）：

    旧 namespace / 旧 J### / 旧资源私有名 / 错误 J### /
    不必要的 player/mod/.../plxxx 模型覆盖 / 悬空路径

硬约束：**NPC texture 原路径中的 NPC ID 是允许项**（workflow §Phase I 明文），
例如 `dddder4/npc709/`。它们不得被当成"旧 ID 残留"清理掉。

扫描范围限 `natives/` + `reframework/`（与 Golden 的
`runtime_residual_scan_scope` 一致）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from pfb_equal_length_replace import extract_utf16_strings  # noqa: E402
from static_validate import HISTORICAL_TOKENS, RESOURCE_EXTS, SCAN_ROOTS  # noqa: E402

# J### 与 JR<role>### token：同时匹配 ASCII 与 UTF-16LE 两种编码
RE_J_ASCII = re.compile(rb"J\d{3}")
RE_J_UTF16 = re.compile(rb"J\x00\d\x00\d\x00\d\x00")
RE_RES_ASCII = re.compile(rb"JR[A-Za-z]{2,4}\d{3}")
RE_RES_UTF16 = re.compile(rb"J\x00R\x00(?:[A-Za-z]\x00){2,4}\d\x00\d\x00\d\x00")

# 允许项：NPC 原始 texture / 模型路径里的 NPC ID
ALLOWED_PATTERNS = (
    re.compile(r"dddder4/npc\d+"),
    re.compile(r"npc\d+_\d+_body"),
    re.compile(r"npc/mod/npc\d+"),
    re.compile(r"nid\d+"),
)
# 目标槽 PFB 路径（例：player/prefab/mod/f/pl279/）是允许项，不属于
# "不必要的 plxxx 模型覆盖"
ALLOWED_OVERRIDE_PREFIX = "natives/STM/player/prefab/mod/f/pl"

# 文本类扩展名：只有这些文件允许用 ASCII 模式扫 token。
# RE Engine 的资源引用字符串是 UTF-16LE；在 BC 压缩纹理等二进制数据里，
# ASCII 的 `J\d{3}` 会大量偶然命中，纯属噪音。
TEXT_EXTS = (".lua", ".json", ".ini", ".txt", ".md")


def tokens_in(data, ascii_ok=False):
    j, res = set(), set()
    if ascii_ok:
        j |= {m.group().decode("ascii", "ignore") for m in RE_J_ASCII.finditer(data)}
        res |= {m.group().decode("ascii", "ignore") for m in RE_RES_ASCII.finditer(data)}
    for m in RE_J_UTF16.finditer(data):
        raw = m.group()
        j.add(bytes(raw[i] for i in range(0, len(raw), 2)).decode("ascii", "ignore"))
    for m in RE_RES_UTF16.finditer(data):
        raw = m.group()
        res.add(bytes(raw[i] for i in range(0, len(raw), 2)).decode("ascii", "ignore"))
    return sorted(j), sorted(res)


def iter_scan_files(candidate):
    candidate = Path(candidate)
    for root in SCAN_ROOTS:
        base = candidate / root
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if p.is_file():
                yield p


def is_allowed(text):
    return any(p.search(text) for p in ALLOWED_PATTERNS)


def fullscan(candidate, asset_id, slot, expected_res_names):
    candidate = Path(candidate)
    num = asset_id[1:]
    expected_j = {asset_id, "J%s" % num}
    expected_res = set(expected_res_names)

    wrong_j, wrong_res, legacy_hits = [], [], []
    allowed_hits, overrides, dangling = [], [], []
    seen_j, seen_res = set(), set()

    for p in iter_scan_files(candidate):
        rel = p.relative_to(candidate).as_posix()
        data = p.read_bytes()
        j, res = tokens_in(data, ascii_ok=rel.endswith(TEXT_EXTS))
        seen_j.update(j)
        seen_res.update(res)

        for tok in j:
            if tok not in expected_j:
                wrong_j.append({"file": rel, "token": tok})
        for tok in res:
            if tok not in expected_res:
                wrong_res.append({"file": rel, "token": tok})

        for tok in HISTORICAL_TOKENS:
            for enc in ("ascii", "utf-16-le"):
                if not rel.endswith(TEXT_EXTS) and enc == "ascii":
                    continue        # 二进制资源只认 UTF-16LE 引用
                try:
                    if tok.encode(enc) in data:
                        legacy_hits.append({"file": rel, "token": tok, "encoding": enc})
                except UnicodeEncodeError:
                    pass

        if rel.startswith("natives/STM/player/mod/") and re.search(r"/pl\d+", rel):
            overrides.append(rel)

        # NPC 原路径允许项：从 PFB / mdf2 的字符串表里收集
        if rel.endswith((".pfb.17", ".mdf2.23", ".chain.48", ".jcns.21")):
            for s in extract_utf16_strings(data):
                t = s["string"]
                if is_allowed(t):
                    allowed_hits.append({"file": rel, "token": t})
                if t.count("/") >= 1 and any(t.endswith(e) for e in RESOURCE_EXTS):
                    if t.startswith(("player/", "dddder4/", "npc/", "systems/")):
                        if t.startswith("systems/"):
                            continue
                        target = candidate / "natives/STM" / t
                        if not (target.parent.is_dir() and any(
                                q.name.startswith(target.name + ".")
                                for q in target.parent.iterdir())):
                            dangling.append({"file": rel, "ref": t})

    return {
        "asset_id": asset_id,
        "target_player_slot": "PL%s" % slot,
        "scan_scope": list(SCAN_ROOTS),
        "expected_j_tokens": sorted(expected_j),
        "expected_resources": sorted(expected_res),
        "observed_j_tokens": sorted(seen_j),
        "observed_resources": sorted(seen_res),
        "wrong_j_tokens": wrong_j,
        "wrong_resource_names": wrong_res,
        "legacy_token_hits": legacy_hits,
        "unnecessary_plxxx_overrides": overrides,
        "dangling_refs": dangling,
        "allowed_npc_path_hits": sorted({a["token"] for a in allowed_hits}),
        "status": "PASS" if not (wrong_j or wrong_res or legacy_hits
                                 or overrides or dangling) else "FAIL",
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Phase I：候选包全包扫描")
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--asset-id", required=True)
    ap.add_argument("--slot", required=True)
    ap.add_argument("--role", action="append", default=["arm", "body", "helm", "wst"],
                    help="该 asset 的私有资源 role（可重复）")
    ap.add_argument("--report-dir", required=True)
    args = ap.parse_args(argv)

    num = args.asset_id[1:]
    expected = ["JR%s%s" % (r, num) for r in args.role]
    res = fullscan(args.candidate, args.asset_id, args.slot, expected)

    out = Path(args.report_dir) / "fullscan.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(res, indent=2, ensure_ascii=False) + "\n")

    print("Phase I 全包扫描: %s" % res["status"])
    print("  scope              : %s" % ", ".join(res["scan_scope"]))
    print("  expected J tokens  : %s" % res["expected_j_tokens"])
    print("  observed J tokens  : %s" % res["observed_j_tokens"])
    print("  expected resources : %s" % res["expected_resources"])
    print("  observed resources : %s" % res["observed_resources"])
    print("  wrong J tokens     : %d" % len(res["wrong_j_tokens"]))
    for w in res["wrong_j_tokens"][:10]:
        print("      %s  %s" % (w["file"], w["token"]))
    print("  wrong resource nm  : %d" % len(res["wrong_resource_names"]))
    for w in res["wrong_resource_names"][:10]:
        print("      %s  %s" % (w["file"], w["token"]))
    print("  legacy token hits  : %d" % len(res["legacy_token_hits"]))
    print("  plxxx overrides    : %d %s" % (len(res["unnecessary_plxxx_overrides"]),
                                            res["unnecessary_plxxx_overrides"][:5]))
    print("  dangling refs      : %d" % len(res["dangling_refs"]))
    for w in res["dangling_refs"][:10]:
        print("      %s  %s" % (w["file"], w["ref"]))
    print("  allowed NPC paths  : %s" % res["allowed_npc_path_hits"])
    print("  report             : %s" % out)
    return 0 if res["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())

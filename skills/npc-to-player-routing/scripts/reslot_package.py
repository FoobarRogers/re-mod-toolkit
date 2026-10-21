#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""改换 test 包的 player 装备 id —— 只改路径，不改内容。

背景（用户 2026-09-25 明确）：

    NPC id ≠ player 装备 id。`npc709` 是源 NPC 的三位 id；
    而一个外观 mod 在玩家侧由某个**防具 id**承载（`pl279` / `pl314` / …）。

    换装备 id 的方法是：改 `pl***` 目录、PFB 目录与 PFB 文件名
    （例如 `player/prefab/mod/f/pl279/f_wst279.pfb.17` → `pl314/f_wst314.pfb.17`）。

    `natives/STM/player/JRRB/J018/JR*.mesh` 这类**私有资源与所属文件夹不改**
    —— 那是 J### 资产身份，与装备 id 无关。

本工具做的事：

    1. 扫描包内所有成员的**字节内容**，只按 **UTF-16LE** 检索旧 slot 的引用串
       （项目纪律：ASCII 扫描在 BC 压缩纹理上必然误报）。
       一旦发现内容引用旧 slot ⇒ 报 MANUAL_REVIEW_REQUIRED 并停止
       （那说明"只改路径"不成立，包内还有需要同步的引用）。
    2. 按路径改名：目录段 `pl<old>` → `pl<new>`，文件名中的 `_<old>.` → `_<new>.`
       （后者同时覆盖 LuaBone custom JSON，如 `f_helm603.json` → `f_helm312.json`）。
    3. 逐成员比对**内容 SHA256**：必须与旧包逐一相同 —— 这是"只改路径"的证明。

不动的东西（硬规则）：

    `natives/STM/player/JRRB/J0##/**`、`natives/STM/npc/**`、
    `natives/STM/dddder4/**`、`reframework/data/LUABoneSystem/custom/JR*.json`

只读源包；输出写到指定路径。不触碰用户游戏目录，不触碰 `base/golden/`。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

# 内容级安全检查用的引用串模板（UTF-16LE）
PROBE_TEMPLATES = ("pl%s", "f_arm%s", "f_body%s", "f_helm%s", "f_leg%s", "f_wst%s", "_%s")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def probe_content(data: bytes, slot: str):
    """内容里是否按 UTF-16LE 引用该 slot。返回命中标签列表。"""
    hits = []
    for tpl in PROBE_TEMPLATES:
        s = tpl % slot
        n = data.count(s.encode("utf-16-le"))
        if n:
            hits.append("%s x%d" % (s, n))
    return hits


def rewrite_path(name: str, old: str, new: str):
    """返回新路径；路径不含旧 slot 时返回 None。

    两条规则，只作用于**路径**：

      1. 目录段 `pl<old>`  → `pl<new>`
         （`natives/STM/player/prefab/mod/f/pl279/...` 或 `.../player/mod/f/pl603/...`）
      2. 文件名里 `<old>.` → `<new>.`（要求前一个字符是字母或下划线）
         这也覆盖 LuaBone custom JSON —— 它的文件名必须等于**部件对象名**，
         而部件对象名来自 mesh 文件名（`f_helm603.mesh` → `f_helm603.json`）。

    刻意**不动**文件名里的 `pl<old>` 前缀形式（如 `pl_face709.mesh`）：
    那是源 NPC 侧资源名，不属于装备 id 承载路径。
    """
    before = name
    name = re.sub(r"(?<=/)pl%s(?=/|$)" % re.escape(old), "pl%s" % new, name)
    name = re.sub(r"(?<=[A-Za-z_])%s\." % re.escape(old), "%s." % new, name)
    return name if name != before else None


def collect(zip_path, old, new):
    """返回 (路径映射, 内容安全检查结果, 成员内容哈希表)。"""
    mapping = {}
    probe = []
    hashes = {}
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            data = z.read(info)
            hashes[info.filename] = _sha(data)
            hits = probe_content(data, old)
            if hits:
                probe.append({"member": info.filename, "hits": hits})
            nn = rewrite_path(info.filename, old, new)
            if nn:
                mapping[info.filename] = nn
    return mapping, probe, hashes


def reslot(zip_path, old, new, out_path, *, dry_run=False, allow_content_refs=False):
    old, new = str(old), str(new)
    if old == new:
        raise SystemExit("旧 slot 与新 slot 相同：%s" % old)

    mapping, probe, hashes = collect(zip_path, old, new)
    if not mapping:
        raise SystemExit("包内没有任何路径引用 slot %s —— 这不是该 slot 的包？" % old)
    if probe and not allow_content_refs:
        print("MANUAL_REVIEW_REQUIRED")
        print("  包内 *内容* 按 UTF-16LE 引用了旧 slot %s：" % old)
        for p in probe:
            print("    %s  ->  %s" % (p["member"], ", ".join(p["hits"])))
        print("  ⇒ 只改路径不足以完成换 id；需先判定这些引用是否需要同步。")
        return 2

    # 目标路径冲突检查
    dupes = {}
    with zipfile.ZipFile(zip_path) as z:
        all_new = []
        for name in z.namelist():
            all_new.append(mapping.get(name, name))
        for n in all_new:
            dupes[n] = dupes.get(n, 0) + 1
    clash = sorted(k for k, v in dupes.items() if v > 1)
    if clash:
        raise SystemExit("改名后出现重复成员路径：%s" % clash)

    if dry_run:
        return {"old_slot": old, "new_slot": new, "dry_run": True,
                "renamed_count": len(mapping), "mapping": mapping}

    out_p = Path(out_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path) as zin, \
         zipfile.ZipFile(out_p, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info)
            if _sha(data) != hashes[info.filename]:
                raise SystemExit("读出的内容与首次扫描不一致：%s" % info.filename)
            new_name = mapping.get(info.filename, info.filename)
            zi = zipfile.ZipInfo(new_name, date_time=info.date_time)
            zi.compress_type = info.compress_type
            zi.external_attr = info.external_attr
            zi.internal_attr = info.internal_attr
            zi.create_system = info.create_system
            zout.writestr(zi, data)

    # 验证：新包的每个成员内容必须与旧包对应成员逐字节相同
    with zipfile.ZipFile(out_p) as z:
        new_hashes = {i.filename: _sha(z.read(i)) for i in z.infolist()}
    reverse = {v: k for k, v in mapping.items()}
    ok = True
    for nn, h in new_hashes.items():
        src = reverse.get(nn, nn)
        if hashes.get(src) != h:
            ok = False
            print("  !! 内容不一致: %s (源 %s)" % (nn, src))
    if set(new_hashes) != {mapping.get(k, k) for k in hashes}:
        ok = False
        print("  !! 成员集合与预期不符")

    return {"old_slot": old, "new_slot": new, "dry_run": False,
            "out": str(out_p), "renamed_count": len(mapping), "mapping": mapping,
            "member_count": len(new_hashes), "content_unchanged": ok}


def main(argv=None):
    ap = argparse.ArgumentParser(description="改换 test 包的 player 装备 id（只改路径，不改内容）")
    ap.add_argument("zip_path")
    ap.add_argument("--from", dest="old", required=True, help="旧防具 id 数字，如 279")
    ap.add_argument("--to", dest="new", required=True, help="新防具 id 数字，如 314")
    ap.add_argument("--out", required=True, help="输出 zip 路径")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--allow-content-refs", action="store_true",
                    help="研究用：即使内容引用了旧 slot 也继续（默认停止）")
    ap.add_argument("--json", help="把结果写成 JSON")
    args = ap.parse_args(argv)

    result = reslot(args.zip_path, args.old, args.new, args.out,
                    dry_run=args.dry_run, allow_content_refs=args.allow_content_refs)
    if isinstance(result, int):
        return result

    if args.json:
        p = Path(args.json)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8", newline="\n")

    if result.get("dry_run"):
        print("DRY-RUN  pl%s -> pl%s，将改路径 %d 条：" % (args.old, args.new, result["renamed_count"]))
        for a, b in result["mapping"].items():
            print("  %s\n    -> %s" % (a, b))
        return 0

    print("换 id 完成（只改路径，内容逐字节不变）")
    print("  pl%s -> pl%s" % (result["old_slot"], result["new_slot"]))
    print("  改路径 %d 条 / 成员 %d 个" % (result["renamed_count"], result["member_count"]))
    print("  内容逐成员一致: %s" % result["content_unchanged"])
    print("  输出: %s" % result["out"])
    if not result["content_unchanged"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

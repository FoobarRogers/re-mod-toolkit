#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test 包命名规范 —— 生成包名与可验证重命名。

规范（`docs/project-workflow.md` §「test 包命名规范」）：

    [test]NPC<npcid>_<测试内容>_PL<slot>.zip

    [test]     固定 tag，取代源 mod 系列的 `[Umamusume NPC*]`
    NPC<npcid> 源 NPC 的三位 id，**保持不动**（如 NPC709、NPC714）
    <测试内容> 本次测试的相对变量描述；`test1` = 基线，之后写清**唯一**变量
    PL<slot>   目标防具 ID（如 PL279 / PL423 / PL603）

两个子命令：

    name    按规范拼出包名（供其它脚本 / 人工引用，不触碰文件）
    rename  把已有 zip 改成规范名，并同步 `.manifest.json` / `.sha256` 伴随文件

`rename` 的铁律：**只改文件名，不改包内容**。执行前后会比对 zip 的 SHA256
与成员表（文件名 / CRC / 大小），任何一项不一致即报错并回滚本轮改名。

只写 `dist/` 与工作区；不触碰用户游戏目录，不触碰 `base/golden/`。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

NAME_RE = re.compile(r"^\[test\]NPC(\d{3})_(.+)_PL(\d+)\.zip$")
SIDECARS = (".manifest.json", ".sha256")


def build_name(npc_id, content, slot) -> str:
    """按规范拼包名。输入容错：接受 `709` / `NPC709` / `npc709`，接受 `279` / `PL279`。"""
    npc = re.sub(r"^[Nn][Pp][Cc]", "", str(npc_id)).strip()
    if not re.fullmatch(r"\d{1,3}", npc):
        raise SystemExit("npc_id 必须是 1–3 位数字（或 NPC### 形式），收到 %r" % npc_id)
    slot = re.sub(r"^[Pp][Ll]", "", str(slot)).strip()
    if not re.fullmatch(r"\d{1,4}", slot):
        raise SystemExit("slot 必须是数字（或 PL### 形式），收到 %r" % slot)
    content = str(content).strip()
    if not content or "/" in content or "\\" in content or ":" in content:
        raise SystemExit("测试内容不能为空、不能含路径分隔符：%r" % content)
    return "[test]NPC%s_%s_PL%s.zip" % (npc.zfill(3), content, slot)


def parse_name(filename):
    m = NAME_RE.match(Path(filename).name)
    if not m:
        return None
    return {"npc_id": m.group(1), "content": m.group(2), "slot": m.group(3)}


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _members(path):
    with zipfile.ZipFile(path) as z:
        return [(i.filename, i.CRC, i.file_size) for i in z.infolist()]


def rename(old, new, *, dry_run=False):
    """改名并同步伴随文件。返回对照记录；任何内容变化都是错误。"""
    old_p, new_p = Path(old), Path(new)
    if not old_p.exists():
        raise SystemExit("源包不存在：%s" % old_p)
    if old_p.resolve() == new_p.resolve():
        return {"old": old_p.name, "new": new_p.name, "already_compliant": True,
                "sha256": _sha256(old_p), "member_count": len(_members(old_p)),
                "content_unchanged": True}
    if new_p.exists():
        raise SystemExit("目标名已被占用：%s" % new_p)

    before = {"sha256": _sha256(old_p), "members": _members(old_p)}
    moved = []

    if dry_run:
        plan = [str(old_p)]
        plan += [str(old_p) + s for s in SIDECARS if Path(str(old_p) + s).exists()]
        return {"old": old_p.name, "new": new_p.name, "dry_run": True,
                "would_move": plan, "before": before}

    try:
        old_p.rename(new_p)
        moved.append((old_p, new_p))

        for suffix in SIDECARS:
            so, sn = Path(str(old_p) + suffix), Path(str(new_p) + suffix)
            if so.exists():
                so.rename(sn)
                moved.append((so, sn))

        man = Path(str(new_p) + ".manifest.json")
        if man.exists():
            d = json.loads(man.read_text(encoding="utf-8"))
            if "archive" in d:
                d["archive"] = new_p.name
                man.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n",
                               encoding="utf-8", newline="\n")

        sh = Path(str(new_p) + ".sha256")
        if sh.exists():
            txt = sh.read_text(encoding="utf-8")
            fixed = txt.replace(old_p.name, new_p.name)
            if fixed != txt:
                sh.write_text(fixed, encoding="utf-8", newline="\n")

        after = {"sha256": _sha256(new_p), "members": _members(new_p)}
        if before != after:
            raise SystemExit(
                "包内容发生变化，拒绝本次改名：sha256 %s -> %s，成员表 %s"
                % (before["sha256"], after["sha256"],
                   "一致" if before["members"] == after["members"] else "不一致"))
    except BaseException:
        for src, dst in reversed(moved):          # 回滚
            if dst.exists() and not src.exists():
                dst.rename(src)
        raise

    return {"old": old_p.name, "new": new_p.name, "dry_run": False,
            "moved": [str(d) for _, d in moved],
            "sha256": after["sha256"], "member_count": len(after["members"]),
            "content_unchanged": True}


def main(argv=None):
    ap = argparse.ArgumentParser(description="test 包命名规范：生成包名 / 可验证重命名")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_name = sub.add_parser("name", help="按规范拼出包名（不触碰文件）")
    p_name.add_argument("--npc-id", required=True, help="源 NPC id，如 709 或 NPC709")
    p_name.add_argument("--content", required=True, help="本次测试内容，如 test2-neckS0")
    p_name.add_argument("--slot", required=True, help="目标防具 ID，如 279 或 PL279")

    p_re = sub.add_parser("rename", help="把已有 zip 改成规范名（不改包内容）")
    p_re.add_argument("zip_path")
    p_re.add_argument("--to", help="显式目标名；省略则由 --npc-id/--content/--slot 拼出")
    p_re.add_argument("--npc-id")
    p_re.add_argument("--content")
    p_re.add_argument("--slot")
    p_re.add_argument("--dry-run", action="store_true")
    p_re.add_argument("--json", help="把结果写成 JSON")

    args = ap.parse_args(argv)

    if args.cmd == "name":
        print(build_name(args.npc_id, args.content, args.slot))
        return 0

    if not args.to:
        if not (args.npc_id and args.content and args.slot):
            raise SystemExit("rename 需要 --to，或同时给出 --npc-id / --content / --slot")
    target = args.to or build_name(args.npc_id, args.content, args.slot)
    target_p = Path(args.zip_path).parent / target

    result = rename(args.zip_path, target_p, dry_run=args.dry_run)
    if args.json:
        p = Path(args.json)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8", newline="\n")

    if result.get("already_compliant"):
        print("已合规，无需改名：" + result["new"])
        print("  成员数 %d，sha256 %s" % (result["member_count"], result["sha256"]))
        return 0

    if result["dry_run"]:
        print("DRY-RUN：将移动")
        for f in result["would_move"]:
            print("  " + f)
        print("到 " + target)
        return 0

    print("改名完成（包内容逐字节不变）")
    print("  %s -> %s" % (result["old"], result["new"]))
    print("  成员数 %d，sha256 %s" % (result["member_count"], result["sha256"]))
    for f in result["moved"]:
        print("  伴随文件: " + f)
    return 0


if __name__ == "__main__":
    sys.exit(main())

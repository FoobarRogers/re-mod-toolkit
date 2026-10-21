#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase G —— PFB 等长资源字符串改写。

原则（`docs/NPC_TO_PLAYER_CONVERSION_WORKFLOW_v0.2-draft.md` §Phase G）：

    Minimum Rewrite / Equal-Length Preferred / No Blind Numeric Replace /
    Explain Every Changed Region

本工具只做一件事：把 PFB 中**已声明**的 UTF-16LE 资源 token 做等长替换，
并解释每一处改动落在哪个字符串的哪个偏移上。它不做"看起来像编号"的模糊
数字替换，也不改 PFB 的层级结构、component 与未知字段。

硬 STOP（审查意见 §12 / workflow §5）：
  - 任一替换对 old/new 字节长度不等（会破坏偏移）
  - 同一文件内命中区间发生重叠（无法解释改动归属）
  - 改写后文件大小变化
  - 改写后仍残留被替换掉的旧 token
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

DEFAULT_ENCODING = "utf-16-le"


class ManualReviewRequired(Exception):
    """命中硬 STOP 条件，不继续自动改写。"""


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def extract_utf16_strings(data, min_len=4):
    """抽取 UTF-16LE 可打印串（PFB 内字符串无 NUL 终止、靠 0x00 填充对齐）。"""
    out, cur, start = [], [], None
    for i in range(0, len(data) - 1, 2):
        ch = data[i] | (data[i + 1] << 8)
        if 0x20 <= ch < 0x7F:
            if start is None:
                start = i
            cur.append(chr(ch))
        else:
            if start is not None and len(cur) >= min_len:
                out.append({"offset": "0x%x" % start, "string": "".join(cur)})
            start, cur = None, []
    if start is not None and len(cur) >= min_len:
        out.append({"offset": "0x%x" % start, "string": "".join(cur)})
    return out


def plan_replacements(data, pairs, encoding, path):
    """收集所有命中区间；不等长或重叠即 STOP。"""
    spans = []
    counts = {}
    for old, new in pairs:
        ob, nb = old.encode(encoding), new.encode(encoding)
        if len(ob) != len(nb):
            raise ManualReviewRequired(
                "%s: 替换 %r -> %r 字节长度不等 (%d vs %d)，会破坏后续偏移"
                % (path, old, new, len(ob), len(nb))
            )
        n, start = 0, 0
        while True:
            i = data.find(ob, start)
            if i < 0:
                break
            spans.append((i, i + len(ob), old, new))
            n += 1
            start = i + 1
        if n:
            counts["%s->%s" % (old, new)] = n

    spans.sort()
    for a, b in zip(spans, spans[1:]):
        if b[0] < a[1]:
            raise ManualReviewRequired(
                "%s: 替换区间重叠 (%s @%d-%d 与 %s @%d-%d)，改动归属无法解释"
                % (path, a[2], a[0], a[1], b[2], b[0], b[1])
            )
    return spans, counts


def rewrite(data, spans):
    out = bytearray(data)
    for start, end, old, new in spans:
        nb = new.encode(DEFAULT_ENCODING)
        out[start:end] = nb
    return bytes(out)


def run(in_dir, out_dir, pairs, filename_pairs, report_dir, encoding=DEFAULT_ENCODING,
        ref_root=None):
    in_dir, out_dir = Path(in_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if report_dir:
        Path(report_dir).mkdir(parents=True, exist_ok=True)

    if not in_dir.is_dir():
        raise ManualReviewRequired("输入目录不存在: %s" % in_dir)

    files = sorted(p for p in in_dir.iterdir() if p.is_file())
    if not files:
        raise ManualReviewRequired("输入目录内没有文件: %s" % in_dir)

    report, after_refs = [], []
    for src in files:
        raw = src.read_bytes()
        spans, counts = plan_replacements(raw, pairs, encoding, src.name)
        new = rewrite(raw, spans)
        if len(new) != len(raw):
            raise ManualReviewRequired("%s: 改写后大小变化 %d -> %d" % (src.name, len(raw), len(new)))

        residual = {}
        for old, newtok in pairs:
            ob = old.encode(encoding)
            if ob and ob in new:
                residual[old] = new.count(ob)
        if residual:
            raise ManualReviewRequired("%s: 改写后仍残留旧 token %s" % (src.name, residual))

        dst_name = src.name
        for old, newtok in filename_pairs:
            dst_name = dst_name.replace(old, newtok)
        dst = out_dir / dst_name
        dst.write_bytes(new)

        # changed_byte_count 语义对齐 Golden 的 pfb-rewrite-report：
        # 统计**逐字节实际差异数**（相同字符不计数），而不是替换区间的字节长度。
        declared = set()
        for start, end, _, _ in spans:
            declared.update(range(start, end))
        changed_offsets = {i for i, (a, b) in enumerate(zip(raw, new)) if a != b}
        unexpected = sorted(changed_offsets - declared)

        ref = Path(ref_root) if ref_root else out_dir
        try:
            rel_path = dst.relative_to(ref).as_posix()
        except ValueError:
            rel_path = dst.as_posix()

        report.append({
            "file": rel_path,
            "source_file": src.name,
            "size_before": len(raw),
            "size_after": len(new),
            "mapping_counts": counts,
            "residual_old_tokens": residual,
            "changed_byte_count": len(changed_offsets),
            "unexpected_changed_byte_count": len(unexpected),
            "unexpected_changed_offsets": ["0x%x" % o for o in unexpected],
            "changed_regions": [
                {"offset": "0x%x" % s, "old": o, "new": n} for s, _, o, n in spans
            ],
            "source_sha256": sha256(raw),
            "output_sha256": sha256(new),
        })
        after_refs.append({
            "file": rel_path,
            "source_sha256": sha256(raw),
            "normalized_sha256": sha256(new),
            "relevant_strings_after": [
                s for s in extract_utf16_strings(new)
                if "/" in s["string"] or s["string"].startswith("JR")
            ],
        })

    if report_dir:
        rd = Path(report_dir)
        with open(rd / "pfb-rewrite-report.json", "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        with open(rd / "pfb-after-refs.json", "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(after_refs, indent=2, ensure_ascii=False) + "\n")
        lines = []
        for r in report:
            lines.append("== %s" % r["file"])
            lines.append("   size %d -> %d  (changed bytes: %d)"
                         % (r["size_before"], r["size_after"], r["changed_byte_count"]))
            for k, v in sorted(r["mapping_counts"].items()):
                lines.append("   %-28s x%d" % (k, v))
            for c in r["changed_regions"]:
                lines.append("   @%s  %s -> %s" % (c["offset"], c["old"], c["new"]))
        with open(rd / "pfb-rewrite-report.txt", "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + "\n")

    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description="Phase G：PFB 等长资源字符串改写")
    ap.add_argument("--in-dir", required=True, help="源 PFB 目录（例如 Golden 的 pl423/）")
    ap.add_argument("--out-dir", required=True, help="目标 PFB 目录（例如候选包的 pl279/）")
    ap.add_argument("--replace", action="append", default=[],
                    help="内容等长替换 OLD=NEW（可重复）")
    ap.add_argument("--filename-replace", action="append", default=[],
                    help="文件名替换 OLD=NEW（可重复）")
    ap.add_argument("--report-dir", help="报告输出目录")
    args = ap.parse_args(argv)

    def pairs_of(items, label):
        out = []
        for it in items:
            if "=" not in it:
                print("参数格式错误（需要 OLD=NEW）: %r" % it)
                raise SystemExit(4)
            o, n = it.split("=", 1)
            out.append((o, n))
        return out

    content_pairs = pairs_of(args.replace, "replace")
    name_pairs = pairs_of(args.filename_replace, "filename-replace")

    try:
        report = run(args.in_dir, args.out_dir, content_pairs, name_pairs, args.report_dir)
    except ManualReviewRequired as exc:
        print("MANUAL_REVIEW_REQUIRED")
        print("  " + str(exc))
        return 2

    print("Phase G PFB 改写 PASS")
    print("  in-dir  : %s" % args.in_dir)
    print("  out-dir : %s" % args.out_dir)
    print("  files   : %d" % len(report))
    for r in report:
        print("    %-34s %d -> %d bytes, changed %d, unexpected %d"
              % (r["source_file"], r["size_before"], r["size_after"],
                 r["changed_byte_count"], r["unexpected_changed_byte_count"]))
        for k, v in sorted(r["mapping_counts"].items()):
            print("        %-28s x%d" % (k, v))
    return 0


if __name__ == "__main__":
    sys.exit(main())

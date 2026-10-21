#!/usr/bin/env python3
"""Create a bounded Markdown summary of REFramework or Lua text logs."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path
import re
import sys


SIGNAL_RE = re.compile(
    r"\b(error|exception|traceback|failed|failure|warning|warn|invalid|nil|assert)\b",
    re.IGNORECASE,
)
TIME_RE = re.compile(r"^\s*(?:\[?\d{1,4}[-/:T .]\d[^\]]*\]?\s*)+")
HEX_RE = re.compile(r"0x[0-9a-f]+", re.IGNORECASE)
NUMBER_RE = re.compile(r"\b\d+\b")


def decode_log(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-16", "utf-8", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def signature(line: str) -> str:
    value = TIME_RE.sub("", line.strip())
    value = HEX_RE.sub("0xADDR", value)
    value = NUMBER_RE.sub("N", value)
    return value[:300] or "<blank>"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("--module", help="Keep signals whose nearby context mentions this text")
    parser.add_argument("--context", type=int, default=1, help="Lines before and after each representative hit")
    parser.add_argument("--max-groups", type=int, default=8, help="Maximum distinct signatures in the report")
    parser.add_argument("--output", type=Path, help="Write Markdown here; otherwise print it")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.context < 0 or args.max_groups < 1:
        raise ValueError("context must be non-negative and max-groups must be positive")

    lines = decode_log(args.log).splitlines()
    hits: list[int] = []
    for index, line in enumerate(lines):
        if not SIGNAL_RE.search(line):
            continue
        start = max(0, index - max(args.context, 3))
        end = min(len(lines), index + max(args.context, 3) + 1)
        if args.module and args.module.lower() not in "\n".join(lines[start:end]).lower():
            continue
        hits.append(index)

    groups: dict[str, list[int]] = defaultdict(list)
    for index in hits:
        groups[signature(lines[index])].append(index)

    ordered = sorted(groups.items(), key=lambda item: (-len(item[1]), item[1][0]))[: args.max_groups]
    signal_words = Counter(match.group(1).lower() for index in hits for match in SIGNAL_RE.finditer(lines[index]))

    report: list[str] = [
        "# Log summary",
        "",
        f"- File: `{args.log.name}`",
        f"- Total lines: {len(lines)}",
        f"- Signal lines: {len(hits)}",
        f"- Distinct signatures: {len(groups)}",
        f"- Module filter: `{args.module or 'none'}`",
        f"- Signal counts: {', '.join(f'{key}={value}' for key, value in signal_words.most_common()) or 'none'}",
        "",
    ]

    if not ordered:
        report.extend(["No matching error or warning signals were found.", ""])
    else:
        report.append("## Top signatures")
        report.append("")
        for number, (key, indices) in enumerate(ordered, 1):
            first = indices[0]
            start = max(0, first - args.context)
            end = min(len(lines), first + args.context + 1)
            report.extend(
                [
                    f"### {number}. Occurrences: {len(indices)}; first line: {first + 1}",
                    "",
                    "Signature: `" + key.replace("`", "'") + "`",
                    "",
                    "```text",
                ]
            )
            report.extend(f"{index + 1}: {lines[index]}" for index in range(start, end))
            report.extend(["```", ""])

    output = "\n".join(report).rstrip() + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
        print(f"Summary: {args.output}")
        print(f"Signal lines: {len(hits)}; distinct signatures: {len(groups)}")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)

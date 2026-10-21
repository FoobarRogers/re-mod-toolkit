#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ZCode Large File Guard (Python 版)

与同目录 large-file-guard.mjs v0.2 逻辑等价，改用 Python 运行 ——
因为 ZCode 的 process 型 hook 直接按 argv 执行、不经过 shell，
配置里的 "command": "node" 要求 node 在系统 PATH 中，而本机未安装 node，
hook 进程从未启动（ZCode 日志记 Hook execution failed）。

Usage:
    python large-file-guard.py [maxFullReadBytes] [maxPartialLines] [maxVisualEvidenceBytes]

Recommended:
    maxFullReadBytes       = 65536   (64 KiB)
    maxPartialLines        = 120
    maxVisualEvidenceBytes = 262144  (256 KiB)

Principles:
- Ordinary files keep the strict 64 KiB full-read gate.
- MCP-generated visual evidence images get a separate 256 KiB gate.
- Large full Reads are blocked.
- Bounded partial Reads of large files are allowed.
- Obvious raw shell dumps are blocked.
- Local filtering/indexing tools remain available to data-researcher.
"""

import json
import os
import sys

# ZCode 的 hook 输入是 utf8 一行 JSON；Windows 上 Python 默认编码可能是 GBK，
# 必须显式改 utf8，否则中文路径会解析失败。
if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_MAX_FULL_READ_BYTES = 64 * 1024
DEFAULT_MAX_PARTIAL_LINES = 120
DEFAULT_MAX_VISUAL_EVIDENCE_BYTES = 256 * 1024

VISUAL_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def positive_int(value, fallback):
    if value is None:
        return fallback
    try:
        n = float(str(value).strip())
    except (TypeError, ValueError):
        return fallback
    if n != n or n in (float("inf"), float("-inf")) or n <= 0:
        return fallback
    return int(n)


def _arg_or_env(argv, index, env_name):
    if len(argv) > index and argv[index] != "":
        return argv[index]
    return os.environ.get(env_name)


argv = sys.argv[1:]
MAX_FULL_READ_BYTES = positive_int(
    _arg_or_env(argv, 0, "ZCODE_LARGE_FILE_GUARD_BYTES"), DEFAULT_MAX_FULL_READ_BYTES
)
MAX_PARTIAL_LINES = positive_int(
    _arg_or_env(argv, 1, "ZCODE_LARGE_FILE_GUARD_LINES"), DEFAULT_MAX_PARTIAL_LINES
)
MAX_VISUAL_EVIDENCE_BYTES = positive_int(
    _arg_or_env(argv, 2, "ZCODE_VISUAL_EVIDENCE_GUARD_BYTES"),
    DEFAULT_MAX_VISUAL_EVIDENCE_BYTES,
)


def human_bytes(n):
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    v = float(n)
    i = 0
    while v >= 1024 and i < len(units) - 1:
        v /= 1024.0
        i += 1
    return ("%d %s" % (v, units[i])) if i == 0 else ("%.2f %s" % (v, units[i]))


def resolve_file(cwd, raw_path):
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    p = raw_path.strip()
    if len(p) >= 2 and p[0] == p[-1] and p[0] in ("'", '"'):
        p = p[1:-1]
    if p.startswith("~/") or p.startswith("~\\"):
        home = os.environ.get("USERPROFILE") or os.environ.get("HOME")
        if home:
            p = os.path.join(home, p[2:])
    if not os.path.isabs(p):
        p = os.path.join(cwd or os.getcwd(), p)
    return os.path.normpath(p)


def stat_regular_file(cwd, raw_path):
    full = resolve_file(cwd, raw_path)
    if not full:
        return None
    try:
        size = os.path.getsize(full)
        if not os.path.isfile(full):
            return None
        return {"full": full, "size": size}
    except OSError:
        return None


def is_visual_evidence_file(path):
    """只给视觉 MCP 产出的证据图放宽门禁，不放宽普通图片。"""
    if not isinstance(path, str) or not path:
        return False
    norm = os.path.normpath(path).lower()
    name = os.path.basename(norm)
    ext = os.path.splitext(name)[1]
    if ext not in VISUAL_IMAGE_EXTENSIONS:
        return False
    return (
        "_spike" in name
        or "_marked" in name
        or "glm_vision_marks" in norm
    )


def full_read_limit_for(path):
    return (MAX_VISUAL_EVIDENCE_BYTES
            if is_visual_evidence_file(path) else MAX_FULL_READ_BYTES)


def emit_deny(reason, context):
    sys.stdout.write(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                    "additionalContext": context,
                }
            },
            ensure_ascii=False,
        )
    )


def get_read_path(tool_input):
    if not isinstance(tool_input, dict):
        return None
    for key in ("file_path", "filePath", "path", "filename"):
        if tool_input.get(key):
            return tool_input[key]
    return None


def get_read_limit(tool_input):
    if not isinstance(tool_input, dict):
        return None
    raw = None
    for key in ("limit", "line_limit", "lineLimit"):
        if tool_input.get(key) is not None:
            raw = tool_input[key]
            break
    if raw is None:
        return None
    try:
        n = int(float(str(raw).strip()))
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def get_bash_command(tool_input):
    if not isinstance(tool_input, dict):
        return ""
    for key in ("command", "cmd", "script"):
        if tool_input.get(key):
            return str(tool_input[key])
    return ""


# Conservative raw-dump detection. Pipelines/redirection are allowed so local
# filtering/indexing stays usable. Not a complete shell parser.
RAW_DUMP_TOOLS = ("cat", "type", "more", "get-content", "gc")


def obvious_raw_dump_target(command):
    s = command.strip()
    if not s:
        return None
    # A pipeline or redirection may be doing local filtering/output-to-file.
    if "|" in s or ">" in s:
        return None
    if ";" in s.rstrip(";").replace(";", "", 1):
        pass  # allow a single trailing ';', reject chains below
    body = s.rstrip(";").strip()
    if ";" in body:
        return None
    parts = body.split()
    if len(parts) != 2:
        return None
    tool = parts[0].lower()
    if tool not in RAW_DUMP_TOOLS:
        return None
    target = parts[1].strip()
    if len(target) >= 2 and target[0] == target[-1] and target[0] in ("'", '"'):
        target = target[1:-1]
    return target or None


def main():
    try:
        raw_input = sys.stdin.read()
    except Exception:
        return 0

    try:
        payload = json.loads(raw_input)
    except Exception:
        # Fail open: a broken guard must not break ZCode.
        return 0

    if not isinstance(payload, dict):
        return 0

    event_name = payload.get("hook_event_name") or payload.get("hookEventName")
    if event_name != "PreToolUse":
        return 0

    tool_name = payload.get("tool_name") or payload.get("toolName") or ""
    tool_input = payload.get("tool_input") or payload.get("toolInput") or {}
    cwd = payload.get("cwd") or os.getcwd()

    if tool_name == "Read":
        info = stat_regular_file(cwd, get_read_path(tool_input))
        if not info:
            return 0
        max_read_bytes = full_read_limit_for(info["full"])
        if info["size"] <= max_read_bytes:
            return 0

        limit = get_read_limit(tool_input)

        # Large file + bounded partial read: allow only if the window is small.
        if limit is not None and limit <= MAX_PARTIAL_LINES:
            return 0

        if limit is not None and limit > MAX_PARTIAL_LINES:
            emit_deny(
                "Blocked oversized partial Read: %d lines requested from %s file %s"
                % (limit, human_bytes(info["size"]), info["full"]),
                "Use a smaller bounded Read (<= %d lines), or delegate to @data-researcher. "
                "For large structured data, filter/index locally and return only the relevant "
                "records (normally ~2,000 tokens or less)." % MAX_PARTIAL_LINES,
            )
            return 0

        emit_deny(
            "Blocked full Read of large file (%s > %s): %s"
            % (human_bytes(info["size"]), human_bytes(max_read_bytes), info["full"]),
            "Do not load this file wholesale into model context. Delegate to @data-researcher, "
            "or use a local streaming/filter/index script. If you only need a known section, "
            "use a bounded Read of <= %d lines." % MAX_PARTIAL_LINES,
        )
        return 0

    if tool_name == "Bash":
        target = obvious_raw_dump_target(get_bash_command(tool_input))
        if not target:
            return 0

        info = stat_regular_file(cwd, target)
        if not info:
            return 0
        max_read_bytes = full_read_limit_for(info["full"])
        if info["size"] <= max_read_bytes:
            return 0

        emit_deny(
            "Blocked raw shell dump of large file (%s > %s): %s"
            % (human_bytes(info["size"]), human_bytes(max_read_bytes), info["full"]),
            "Do not print this file wholesale to stdout. Use @data-researcher or locally "
            "filter/index it first (rg/grep/jq/Python/SQLite/project parser), write full "
            "intermediate results to disk, and return only the minimal matching records.",
        )
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())

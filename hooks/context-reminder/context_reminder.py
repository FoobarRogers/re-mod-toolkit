#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ZCode Context Reminder (PostToolUse 提醒器)

与 zcode-large-file-guard 分层: guard(PreToolUse) 硬拦单笔超大读取,
本 hook(PostToolUse) 低频软提醒上下文水位与工具习惯。
设计红线: 频率极低——每次工具调用最多注入一条提醒, 全会话期望个位数;
绝大多数调用静默退出, 不让 agent 进入警惕模式。

检查器(优先级从高到低, 单次最多命中一条):
  H 硬警告  最近请求 input_tokens >= 450000, 每 +20000 重复
  W 软提醒  >= 250000, 每 +50000 重复 (30 万/50 万坎的提前量, 配合 Discipline §10 上下文管理)
  R 重复读  同文件全文 Read >= 3 次 (去重后每再 +3 次重复)
  B 批量    会话内 Bash 累计 >= 40 次 (去重后每再 +40 次重复)

数据源: ~/.zcode/cli/db/db.sqlite 的 model_usage (误差=当前 turn 内增量,
对 20 万间隔的 gate 足够)。状态: ~/.zcode/cli/exec/context-reminder/<sid>.json
Fail-open: 任何异常静默退出, 不阻塞工具流。
"""

import json
import os
import sqlite3
import sys

if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_DB = os.path.join(
    os.environ.get("USERPROFILE", os.path.expanduser("~")),
    ".zcode", "cli", "db", "db.sqlite",
)
STATE_DIR = os.path.join(
    os.environ.get("USERPROFILE", os.path.expanduser("~")),
    ".zcode", "cli", "exec", "context-reminder",
)
HARD_WATER = 450_000
SOFT_WATER = 250_000
HARD_REPEAT = 20_000
SOFT_REPEAT = 50_000
READ_REPEAT = 3
BASH_WARN = 40
FULL_READ_LIMIT_MAX = 120  # limit 超过此值视为全文读


def load_state(sid):
    path = os.path.join(STATE_DIR, sid + ".json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f), path
    except Exception:
        return {}, path


def save_state(path, state):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
    except Exception:
        pass


def last_input_tokens(sid):
    try:
        con = sqlite3.connect(DEFAULT_DB)
        cur = con.cursor()
        cur.execute(
            "SELECT input_tokens FROM model_usage WHERE session_id=? "
            "ORDER BY started_at DESC LIMIT 1", (sid,))
        row = cur.fetchone()
        con.close()
        return (row[0] or 0) if row else 0
    except Exception:
        return 0


def main():
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        return 0
    if not isinstance(payload, dict):
        return 0
    sid = payload.get("sessionId") or payload.get("session_id") or ""
    if not sid:
        return 0
    tool = payload.get("toolName") or payload.get("tool_name") or ""
    tool_input = payload.get("toolInput") or payload.get("tool_input") or {}

    state, state_path = load_state(sid)
    msg = None

    # H/W 水位检查
    water = last_input_tokens(sid)
    if water >= HARD_WATER:
        if water - state.get("hard_warned_at", 0) >= HARD_REPEAT:
            state["hard_warned_at"] = water
            state["soft_warned_at"] = max(state.get("soft_warned_at", 0), water)
            msg = (f"系统警告：当前会话上下文约 {water:,} tokens，已接近 50 万硬上限。"
                   f"必须立即收束：落盘证据，向用户请求 compact 或新会话，"
                   f"不得继续新的大规模调查（Discipline §10 上下文管理）。")
    elif water >= SOFT_WATER:
        if water - state.get("soft_warned_at", 0) >= SOFT_REPEAT:
            state["soft_warned_at"] = water
            msg = (f"系统提醒：当前会话上下文约 {water:,} tokens，接近 30 万软阈值。"
                   f"请完成当前最小闭环，把中间结论落盘，然后向用户提议 compact 或新会话"
                   f"（Discipline §10 上下文管理）。")

    # R 重复全文读取
    if msg is None and tool == "Read":
        fp = str(tool_input.get("file_path", "")) if isinstance(tool_input, dict) else ""
        limit = tool_input.get("limit") if isinstance(tool_input, dict) else None
        is_full = fp and (limit is None or str(limit).strip() == "" or
                          _to_int(limit) > FULL_READ_LIMIT_MAX)
        if is_full:
            reads = state.setdefault("reads", {})
            n = reads.get(fp, 0) + 1
            reads[fp] = n
            if n == READ_REPEAT or (n > READ_REPEAT and (n - READ_REPEAT) % READ_REPEAT == 0):
                msg = (f"系统提醒：{os.path.basename(fp)} 已被第 {n} 次全文读取。"
                       f"改用 offset/limit 片段读取或 git diff 查看变化，"
                       f"避免重复载入（token-discipline 工具调用节）。")

    # B 批量 Bash
    if msg is None and tool == "Bash":
        n = state.get("bash_count", 0) + 1
        state["bash_count"] = n
        if n >= BASH_WARN and (n - BASH_WARN) % BASH_WARN == 0:
            msg = (f"系统提醒：本会话 Bash 已累计 {n} 次。同类只读观测请合并为一次"
                   f"批量脚本执行，stdout 只返回统计与关键命中（Discipline §10 工具经济）。")

    if msg:
        save_state(state_path, state)
        sys.stdout.write(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": msg,
            }
        }, ensure_ascii=False))
    else:
        save_state(state_path, state)
    return 0


def _to_int(v):
    try:
        return int(float(str(v).strip()))
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())

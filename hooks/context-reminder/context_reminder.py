#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ZCode Context Reminder (PostToolUse 提醒器)

与 zcode-large-file-guard 分层: guard(PreToolUse) 硬拦单笔超大读取,
本 hook(PostToolUse) 低频软提醒上下文水位与工具习惯。
设计红线: 频率极低——每次工具调用最多注入一条提醒, 全会话期望个位数;
绝大多数调用静默退出, 不让 agent 进入警惕模式。

检查器(优先级从高到低, 单次最多命中一条):
  W/H 水位  档位按主 agent 模型分档(见 WATER_PROFILES):
            DeepSeek 25 万软提醒(提前量, 每+5万重复)+45 万硬警告(每+2万重复),
            配合其 discipline §10 上下文管理特化条款;
            其它模型(GLM 等)无提前量, 仅 30 万/50 万到点提醒(每+10万/+2万重复)
            ——"接近阈值"式提前催促会使 GLM 过度紧张(2026-10-26 用户裁定)。
            30/50 万坎语义: 到点提议 compact / 必须请求收束。
  R 重复读  同文件全文 Read >= 3 次 (去重后每再 +3 次重复; 模型无关)
  B 批量    会话内 Bash 累计 >= 40 次 (去重后每再 +40 次重复; 模型无关)

数据源: ~/.zcode/cli/db/db.sqlite 的 model_usage (主 agent agent='zcode-agent'
最近一条; 误差=当前 turn 内增量, 对 20 万间隔的 gate 足够)。
状态: ~/.zcode/cli/exec/context-reminder/<sid>.json
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
# 水位档位: DeepSeek 带 25 万提前量软提醒(其 discipline §10 上下文管理特化条款);
# 其它模型(如 GLM)无提前量, 仅在 30 万/50 万到点提醒——"接近阈值"式提前催促
# 会使 GLM 过度紧张(2026-10-26 用户裁定)。30/50 万坎语义: 到点提议 compact /
# 必须请求收束(压缩上下文前先持久化见各版 discipline §10)。
WATER_PROFILES = {
    "deepseek": {
        "soft": 250_000, "soft_repeat": 50_000,
        "soft_msg": ("系统提醒：当前会话上下文约 {water:,} tokens，接近 30 万软阈值。"
                     "请完成当前最小闭环，把中间结论落盘，然后向用户提议 compact 或新会话"
                     "（Discipline §10 上下文管理）。"),
        "hard": 450_000, "hard_repeat": 20_000,
        "hard_msg": ("系统警告：当前会话上下文约 {water:,} tokens，已接近 50 万硬上限。"
                     "必须立即收束：落盘证据，向用户请求 compact 或新会话，"
                     "不得继续新的大规模调查（Discipline §10 上下文管理）。"),
    },
    "default": {
        "soft": 300_000, "soft_repeat": 100_000,
        "soft_msg": ("系统提醒：当前会话上下文约 {water:,} tokens，已到 30 万 compact 坎。"
                     "请把中间结论落盘，向用户提议 compact 或新会话"
                     "（Discipline §10：压缩上下文前先持久化）。"),
        "hard": 500_000, "hard_repeat": 20_000,
        "hard_msg": ("系统警告：当前会话上下文约 {water:,} tokens，已到 50 万坎。"
                     "必须立即收束：落盘证据，向用户请求 compact 或新会话，"
                     "不得继续新的大规模调查（Discipline §10）。"),
    },
}
READ_REPEAT = 3
BASH_WARN = 40
FULL_READ_LIMIT_MAX = 120  # limit 超过此值视为全文读


def water_profile(model_id):
    for key, prof in WATER_PROFILES.items():
        if key != "default" and key in model_id.casefold():
            return prof
    return WATER_PROFILES["default"]


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


def last_main_usage(sid):
    """主 agent (agent='zcode-agent') 最近一次请求的 (input_tokens, model_id)。

    取不到主 agent 行时返回 (0, ""): 水位提醒宁漏勿扰, 与 fail-open 一致。
    """
    try:
        con = sqlite3.connect(DEFAULT_DB)
        cur = con.cursor()
        cur.execute(
            "SELECT input_tokens, model_id FROM model_usage "
            "WHERE session_id=? AND agent='zcode-agent' "
            "ORDER BY started_at DESC LIMIT 1", (sid,))
        row = cur.fetchone()
        con.close()
        return (row[0] or 0), str(row[1] or "")
    except Exception:
        return 0, ""


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

    # H/W 水位检查(档位按主 agent 模型, 见 WATER_PROFILES)
    water, model_id = last_main_usage(sid)
    prof = water_profile(model_id)
    if water >= prof["hard"]:
        if water - state.get("hard_warned_at", 0) >= prof["hard_repeat"]:
            state["hard_warned_at"] = water
            state["soft_warned_at"] = max(state.get("soft_warned_at", 0), water)
            msg = prof["hard_msg"].format(water=water)
    elif water >= prof["soft"]:
        if water - state.get("soft_warned_at", 0) >= prof["soft_repeat"]:
            state["soft_warned_at"] = water
            msg = prof["soft_msg"].format(water=water)

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

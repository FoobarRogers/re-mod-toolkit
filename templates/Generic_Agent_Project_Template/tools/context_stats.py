#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""会话上下文统计（ZCode db.sqlite 审计探针）

用法:
    python context_stats.py <session_id 或前缀> [--db <db.sqlite 路径>]

输出遵循 token-discipline 默认输出协议: 统计、top 项与短结论，
不打印全量消息内容。完整数据以 db.sqlite 为权威源。

用途: 上下文膨胀诊断——逐请求 input 曲线（含 compact 断崖识别）、
工具调用频次与输出体积、Bash 主命令分类。改动前先读本 docstring。
"""

import argparse
import datetime
import json
import os
import re
import sqlite3
import sys
from collections import Counter

DEFAULT_DB = os.path.join(
    os.environ.get("USERPROFILE", os.path.expanduser("~")),
    ".zcode", "cli", "db", "db.sqlite",
)

BASH_BINS = ("cat", "head", "tail", "sed", "grep", "rg", "wc", "ls", "find",
             "echo", "cp", "mv", "mkdir", "git", "diff", "sort", "awk", "tee",
             "rm", "touch", "jq", "timeout", "for", "while")


def ts(ms):
    if not ms:
        return "?"
    return datetime.datetime.fromtimestamp(ms / 1000).strftime("%m-%d %H:%M")


def bash_main_cmd(cmd):
    seg = re.split(r"&&|;", cmd, 1)
    main = seg[1] if len(seg) > 1 and seg[0].strip().startswith("cd") else (seg[0] if seg else "")
    words = main.strip().split()
    if not words:
        return "empty"
    head = words[0].lower().strip("\"'")
    if head in ("python", "python3", "py"):
        script = next((w for w in words[1:] if w.endswith(".py")), "-c/inline")
        return f"python:{os.path.basename(script)}"
    if head in BASH_BINS:
        return head
    return head[:16]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("session")
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    cur = con.cursor()
    cur.execute("SELECT id FROM session WHERE id LIKE ?", ("%" + args.session + "%",))
    rows = cur.fetchall()
    if len(rows) != 1:
        print(f"会话匹配 {len(rows)} 条（需恰好 1 条）: {args.session}")
        for (s,) in rows[:10]:
            print(" ", s)
        return 1
    sid = rows[0][0]

    cwd = ""
    cur.execute("SELECT data FROM message WHERE session_id=? ORDER BY sequence LIMIT 5", (sid,))
    for (data,) in cur.fetchall():
        m = re.search(r'"cwd":"((?:[^"\\]|\\.)*)"', data)
        if m:
            cwd = m.group(1).replace("\\\\", "\\")
            break

    cur.execute("""SELECT count(*), sum(input_tokens), sum(output_tokens), min(started_at), max(started_at)
        FROM turn_usage WHERE session_id=?""", (sid,))
    n_turns, sum_in, sum_out, t0, t1 = cur.fetchone()
    cur.execute("SELECT model_id, count(*) FROM model_usage WHERE session_id=? GROUP BY model_id", (sid,))
    models = ", ".join(f"{m}×{n}" for m, n in cur.fetchall())

    print(f"会话 {sid}")
    print(f"cwd={cwd or '?'}  模型: {models}")
    print(f"turns={n_turns}  turn级input累计={sum_in or 0:,}  output累计={sum_out or 0:,}  跨度 {ts(t0)} ~ {ts(t1)}")

    # 逐 turn 最后请求 input = 该 turn 结束时的上下文
    cur.execute("""SELECT turn_id, max(started_at) FROM model_usage
        WHERE session_id=? AND query_source='main_turn' GROUP BY turn_id ORDER BY max(started_at)""", (sid,))
    turns = cur.fetchall()
    track = []
    for tid, _ in turns:
        cur.execute("""SELECT input_tokens, output_tokens FROM model_usage
            WHERE session_id=? AND turn_id=? AND query_source='main_turn'
            ORDER BY started_at DESC LIMIT 1""", (sid, tid))
        inp, out = cur.fetchone()
        track.append((tid, inp, out))

    print("\n=== 上下文轨迹 (每 turn 末请求 input tokens；<<<<< 为断崖: 比上一点降 >50% 或清零) ===")
    prev = 0
    cliffs = 0
    for tid, inp, out in track:
        drop = prev > 0 and inp < prev * 0.5
        mark = " <<<<<" if drop else ""
        cliffs += 1 if drop else 0
        print(f"  {inp:>9,}  (turn输出 {out:>6,}){mark}")
        prev = inp
    if track:
        print(f"  结论: 起点 {track[0][1]:,} → 终点 {track[-1][1]:,} tokens, 断崖 {cliffs} 次")

    # 工具汇总
    cur.execute("""SELECT tool_name, count(*), sum(output_bytes), max(output_bytes), sum(truncated)
        FROM tool_usage WHERE session_id=? GROUP BY tool_name ORDER BY sum(output_bytes) DESC""", (sid,))
    print(f"\n=== 工具汇总 (top {args.top}, 按输出字节) ===")
    for name, n, ob, mx, tr in cur.fetchall()[: args.top]:
        print(f"  {name:<12} {n:>4} 次  输出 {ob or 0:>10,} B  最大单笔 {mx or 0:>8,} B  截断 {tr or 0}")

    # Bash 主命令分类
    cur.execute("SELECT data FROM part WHERE session_id=?", (sid,))
    kinds, kind_bytes = Counter(), Counter()
    n_tools = 0
    for (data,) in cur.fetchall():
        p = json.loads(data)
        if p.get("type") != "tool" or p.get("tool") != "Bash":
            continue
        n_tools += 1
        st = p.get("state", {})
        cmd = (st.get("input") or {}).get("command", "")
        k = bash_main_cmd(cmd)
        kinds[k] += 1
        kind_bytes[k] += len(st.get("output") or "")
    if n_tools:
        print(f"\n=== Bash {n_tools} 次主命令分类 (top {args.top}, 按次数) ===")
        for k, n in kinds.most_common(args.top):
            print(f"  {n:>4} 次  {kind_bytes[k]:>9,} B  {k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

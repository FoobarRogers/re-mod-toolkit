#!/usr/bin/env python3
"""Query a game's il2cpp_dump.json offline: which type declares a member, what does a
method return, what members does a type have — without launching the game.

Why this exists (paid for over an 8-probe dead end on one project): the last step of
"read the current motion id" hinged on facts a Lua probe cannot tell you — that
`getMotionNode` is declared *only* on `via.motion.TreeLayer`, and that `Motion:get_Layer()`
returns a `WrappedArrayContainer_Layer` (so elements come from get_Count/get_Item, not
get_elements). Each of those facts was decided by one dump query; guessing meant a wasted
in-game run. Rule of thumb: **any "what does this API return" question that a dump can
answer must be answered offline first** — the probe only settles what the dump cannot.

Cost model — the dump is pretty-printed JSON, top-level key = type name, one type after
another (~1.5 GB on MHR):

- Streaming line scan, never `json.load` the whole file, never `grep` (grep cannot tell you
  *which type* a member belongs to, and the encoding/line-length surprises are not worth it).
- A full scan is ~1 minute. If you will query more than twice, run `--build-index` once: it
  writes a compact sidecar (`<dump>.index.json`, tens of MB) and every later query is
  milliseconds. The index is a summary; `--type` on the raw dump still works for full blocks.

Usage:
  python dump_members.py --dump <il2cpp_dump.json> --build-index          # once, then reuse
  python dump_members.py --dump <il2cpp_dump.json> --type via.motion.Motion
  python dump_members.py --dump <il2cpp_dump.json> --type via.motion.Motion --name-like "layer|bank" --show-types
  python dump_members.py --dump <il2cpp_dump.json> --find-member "getMotionNode"   # which type declares it
  python dump_members.py --dump <il2cpp_dump.json> --list-like "^via\\.motion\\."

Container decision rule (the paid-for one): a method's `returns.type` ending in
`*Container*` means elements via `get_Count()` / `get_Item(i)` (0-based); `SystemArray` /
`T[]` means `get_elements()` and never `ipairs`. Two different contracts — check the dump
before writing the probe, not after it returns nothing.

Limits the dump itself has (do not expect more from it):
- No parent-class chains: "does PlayerBase inherit via.Component" is NOT in the dump; the
  deserializer chain must be walked separately, and the final word may still need one probe.
- REFramework's `get_methods()` returns only the class's own methods, so "which layer
  declares member X" must be answered by the full-library `--find-member`, not by querying
  the type you happen to have.
"""
import argparse
import json
import re
import sys
from pathlib import Path

TOP = re.compile(r'^ {4}"([^"]+)": \{$')          # top-level type block
SECTION = re.compile(r'^ {8}"(fields|methods|properties)": \{$')
MEMBER = re.compile(r'^ {12}"([^"]+)": \{$')
INTVAL = re.compile(r'^ {16}"id": (\d+)')
TYPEVAL = re.compile(r'^ {16}"type": "([^"]+)"')
RETURNS = re.compile(r'^ {16}"returns": \{$')
RETTYPE = re.compile(r'^ {20}.*?"type": "([^"]+)"')


def scan_raw(dump, want_types, list_like, find_member, name_like, show_types):
    """One streaming pass over the raw dump. Returns what the query asked for."""
    out, listed, hits = {}, [], []
    cur = sec = member = None
    cur_method = None
    with dump.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            m = TOP.match(line)
            if m:
                cur, sec, member, cur_method = m.group(1), None, None, None
                if list_like and list_like.search(cur) and len(listed) < 400:
                    listed.append(cur)
                if cur in want_types and cur not in out:
                    out[cur] = {"fields": {}, "methods": [], "properties": []}
                continue
            ms = SECTION.match(line)
            if ms:
                sec, member = ms.group(1), None
                continue
            mm = MEMBER.match(line)
            if mm:
                member = mm.group(1)
                cur_method = member if sec == "methods" else None
                if find_member and find_member.search(member) and len(hits) < 300:
                    hits.append((cur, sec, member))
                if cur in out:
                    if sec == "methods":
                        out[cur]["methods"].append({"name": member})
                    elif sec == "properties":
                        out[cur]["properties"].append(member)
                    elif sec == "fields":
                        out[cur]["fields"].setdefault(member, "?")
                continue
            if cur in out and member:
                iv = INTVAL.match(line)
                if iv and sec == "methods" and cur_method is not None:
                    for e in out[cur]["methods"]:
                        if e["name"] == cur_method:
                            e["id"] = int(iv.group(1))
                    continue
                if sec == "fields" and out[cur]["fields"].get(member) in (None, "?"):
                    ft = TYPEVAL.match(line)
                    if ft:
                        out[cur]["fields"][member] = ft.group(1)
                        continue
            if cur in out and sec == "methods" and cur_method is not None and RETURNS.match(line):
                in_ret = True
                # returns block: next "type" line before the closing brace
                ret = None
                for l2 in f:
                    if RETTYPE.match(l2):
                        ret = RETTYPE.match(l2).group(1)
                        break
                    if l2.strip().startswith("}"):
                        break
                for e in out[cur]["methods"]:
                    if e["name"] == cur_method:
                        e["returns"] = ret
                del in_ret
    return out, listed, hits


def build_index(dump, index_path):
    """One full pass -> compact sidecar {type: {members...}}. Later queries: milliseconds."""
    types = {}
    cur = sec = member = cur_method = None
    entry = None
    n = 0
    with dump.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            n += 1
            m = TOP.match(line)
            if m:
                cur, sec, member, cur_method = m.group(1), None, None, None
                entry = None
                types[cur] = {}
                continue
            if cur is None:
                continue
            ms = SECTION.match(line)
            if ms:
                sec, member = ms.group(1), None
                continue
            mm = MEMBER.match(line)
            if mm:
                member = mm.group(1)
                entry = None
                if sec == "methods":
                    entry = {"name": member}
                    types[cur].setdefault("methods", []).append(entry)
                else:
                    types[cur].setdefault(sec, {})[member] = "?" if sec == "fields" else None
                continue
            if member is None:
                continue
            iv = INTVAL.match(line)
            if iv and sec == "methods" and entry is not None:
                entry["id"] = int(iv.group(1))
                continue
            tv = TYPEVAL.match(line)
            if tv and sec == "fields" and types[cur].get("fields", {}).get(member) == "?":
                types[cur]["fields"][member] = tv.group(1)
                continue
            if sec == "methods" and entry is not None and RETURNS.match(line):
                for l2 in f:
                    r = RETTYPE.match(l2)
                    if r:
                        entry["returns"] = r.group(1)
                        break
                    if l2.strip().startswith("}"):
                        break
    index_path.write_text(json.dumps(types, ensure_ascii=False, separators=(",", ":")),
                          encoding="utf-8")
    print(f"索引已建：{index_path}  （类型 {len(types)} 个，扫过 {n:,} 行）")
    print("之后的 --type / --find-member / --list-like 查询走索引，毫秒级。")


def load_index(dump):
    ip = Path(str(dump) + ".index.json")
    if ip.is_file():
        return ip, json.loads(ip.read_text(encoding="utf-8"))
    return None, None


def query_index(types, want_types, list_like, find_member, name_like):
    out, listed, hits = {}, [], []
    for t, body in types.items():
        if list_like and list_like.search(t) and len(listed) < 400:
            listed.append(t)
        if t in want_types:
            out[t] = {"fields": dict(body.get("fields", {})),
                      "methods": [dict(m) for m in body.get("methods", [])],
                      "properties": list(body.get("properties", {}))}
        if find_member:
            if len(hits) < 300:
                for k in body.get("fields", {}):
                    if find_member.search(k) and len(hits) < 300:
                        hits.append((t, "fields", k))
                for k in body.get("properties", {}):
                    if find_member.search(k) and len(hits) < 300:
                        hits.append((t, "properties", k))
            for e in body.get("methods", []):
                nm = e["name"] if isinstance(e, dict) else e
                if find_member.search(nm) and len(hits) < 300:
                    hits.append((t, "methods", nm))
    return out, listed, hits


def report(found, listed, hits, want_types, name_like, show_types, args_find):
    if listed:
        print(f"匹配的类型名 {len(listed)} 个：")
        for t in sorted(listed):
            print("  " + t)
    if hits:
        print(f"\n[反查 {args_find}] 命中 {len(hits)} 条：")
        for cls, sec, member in hits:
            print(f"  {cls:<52} {sec:<11} {member}")
    for t in want_types:
        d = found.get(t)
        if d is None:
            print(f"\n[取不到] {t}")
            continue
        print(f"\n[{t}]")
        rows = []
        for k, v in d["fields"].items():
            rows.append(("field", k, v if show_types else "?"))
        for e in d["methods"]:
            nm = e if isinstance(e, str) else e.get("name", "?")
            extra = []
            if isinstance(e, dict):
                if "id" in e:
                    extra.append(f"id {e['id']}")
                if e.get("returns"):
                    extra.append(f"-> {e['returns']}")
            rows.append(("method", nm, "  ".join(extra)))
        for k in d["properties"]:
            rows.append(("prop", k, ""))
        rows.sort(key=lambda r: r[1].lower())
        for kind, nm, extra in rows:
            if name_like and not name_like.search(nm):
                continue
            tail = f"   {extra}" if extra else ""
            print(f"  [{kind:<5}] {nm}{tail}")


def main():
    ap = argparse.ArgumentParser(description="Offline query over a game's il2cpp_dump.json "
                                             "(which type declares a member / what a method returns)")
    ap.add_argument("--dump", required=True, help="il2cpp_dump.json 路径（或已建索引时，任意一次给过的同路径）")
    ap.add_argument("--build-index", action="store_true", help="一次全扫建紧凑索引（<dump>.index.json），之后查询毫秒级")
    ap.add_argument("--type", action="append", default=[], help="精确类型名，可重复")
    ap.add_argument("--list-like", help="正则：只列匹配的类型名")
    ap.add_argument("--find-member", help="正则：反查哪个类声明了该成员（含父类问题的绕行，见 docstring）")
    ap.add_argument("--name-like", help="正则：只显示匹配的成员名")
    ap.add_argument("--show-types", action="store_true", help="字段显示类型")
    a = ap.parse_args()

    dump = Path(a.dump)
    if not dump.is_file():
        sys.exit(f"✘ 找不到 dump：{dump}")

    if a.build_index:
        build_index(dump, Path(str(dump) + ".index.json"))
        return

    if not (a.type or a.list_like or a.find_member):
        ap.error("至少要给 --type / --list-like / --find-member 之一（建索引用 --build-index）")

    want = set(a.type)
    list_like = re.compile(a.list_like) if a.list_like else None
    find_member = re.compile(a.find_member) if a.find_member else None
    name_like = re.compile(a.name_like) if a.name_like else None

    ip, types = load_index(dump)
    if types is not None:
        print(f"[索引 {ip.name}]")
        found, listed, hits = query_index(types, want, list_like, find_member, name_like)
    else:
        print("[无索引：流式全扫（约 1 分钟）；之后请先 --build-index]", file=sys.stderr)
        found, listed, hits = scan_raw(dump, want, list_like, find_member, name_like, a.show_types)
    report(found, listed, hits, a.type, name_like, a.show_types, a.find_member)


if __name__ == "__main__":
    main()

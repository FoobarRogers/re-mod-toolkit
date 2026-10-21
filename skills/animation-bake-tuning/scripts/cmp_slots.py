#!/usr/bin/env python3
"""Per-bone comparison of two slots in one motlist: WHERE does the difference live?

RMS-per-bone (sorted) tells you the nature of a change between two clips: legs vs upper body
vs `*_T`/`*_W` twist bones. Compare same-length, same-layout clips for conclusions (shorter
clips truncate; quantized slots read garbage — see motlist_lib).

Bone names come from the slot's own skeleton table when it parses; hashes are shown otherwise
so a quantized slot still works for name display even though its R curves must not be compared.

Usage: python cmp_slots.py --motlist <file> --pair 7,9 [--pair 8,9]   (repeatable)
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from motlist_lib import ML, skeleton, q_from_xyz, qang  # noqa: E402


def compare(ml, ia, ib):
    try:
        names = {h: b["name"] for h, b in skeleton(ml.data, ml.starts[ia]).items()}
    except ValueError:
        names = {}
    ca, cb = ml.curves(ia), ml.curves(ib)
    rows = []
    for h in ca:
        if "R" not in ca[h] or "R" not in cb.get(h, {}):
            continue
        ta, va = ca[h]["R"]
        tb, vb = cb[h]["R"]
        n = min(len(ta), len(tb))
        if n < 2:
            continue
        ds = [qang(q_from_xyz(va[k * 3:k * 3 + 3]), q_from_xyz(vb[k * 3:k * 3 + 3])) for k in range(n)]
        rows.append(((sum(d * d for d in ds) / len(ds)) ** 0.5, max(ds),
                     names.get(h, f"hash{h:08x}"), n))
    rows.sort(reverse=True)
    overall = (sum(r[0] ** 2 for r in rows) / len(rows)) ** 0.5 if rows else 0.0
    print(f"=== 槽{ia}({ml.name(ia)}) vs 槽{ib}({ml.name(ib)})   共 {len(rows)} 骨   整体 RMS {overall:.2f} ===")
    for r, mx, nm, n in rows[:14]:
        print(f"   {nm:<16} RMS {r:7.2f}  max {mx:7.2f}  键 {n}")
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--motlist", required=True)
    ap.add_argument("--pair", action="append", required=True, help="i,j — repeatable")
    a = ap.parse_args()
    ml = ML(a.motlist)
    for pair in a.pair:
        ia, ib = (int(x) for x in pair.split(","))
        compare(ml, ia, ib)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()

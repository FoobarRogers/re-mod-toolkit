#!/usr/bin/env python3
"""Slot-vs-slot RMS similarity matrix inside one motlist.

Answers "did the author copy one clip into several slots?" — RMS ~ 0 between two slots means
the same data was written to both (a copy technique); a slot similar to nothing is an
independent rewrite. Rotation-only comparison, so quantized-layout slots will read garbage:
filter by `header_ok` first (see motlist_lib).

Paid-for traps: compare only slots whose layouts match (float vs quantized mix produces fake
distances); clips of different frame counts only compare over the shorter range (the code
samples min(nf) — prefer comparing same-length clips for conclusions).

Usage: python slot_matrix.py --motlist <file> [--slots 7,8,9,27]   (default: all float slots)
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from motlist_lib import ML, q_from_xyz, qang  # noqa: E402


def pose_at(ml, i, f):
    cv = {}
    for t_hash, kinds in ml.curves(i).items():
        for kind, (times, vals) in kinds.items():
            cv.setdefault(t_hash, {})[kind] = (times, vals)
    out = {}
    for h, ks in cv.items():
        if "R" not in ks:
            continue
        times, vals = ks["R"]
        k = 0
        for j, t in enumerate(times):
            if t <= f:
                k = j
        out[h] = q_from_xyz(vals[k * 3:k * 3 + 3])
    return out


def rms(ml, ia, ib):
    nf = min(ml.frames(ia), ml.frames(ib))
    ds = []
    for f in range(0, nf + 1, 2):
        pa, pb = pose_at(ml, ia, f), pose_at(ml, ib, f)
        for h in pa:
            if h in pb:
                ds.append(qang(pa[h], pb[h]) ** 2)
    return (sum(ds) / len(ds)) ** 0.5 if ds else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--motlist", required=True)
    ap.add_argument("--slots", default="", help="comma-separated file-slot indices; default = all float-layout slots")
    a = ap.parse_args()
    ml = ML(a.motlist)

    if a.slots:
        cand = [int(x) for x in a.slots.split(",") if x.strip()]
    else:
        cand = [i for i in range(len(ml.starts)) if ml.is_motion(i) and ml.header_ok(i)]

    print(f"===== {a.motlist} =====")
    print(f"{'槽':>4} {'动作名':<26} {'帧':>5}")
    for i in cand:
        print(f"{i:>4} {ml.name(i):<26} {ml.frames(i):>5}")

    print("\n" + " ".join(f"{i:>8}" for i in cand) + "   (RMS°, 0 = same data)")
    print(" " * 5 + " ".join(f"{ml.name(i)[:8]:>8}" for i in cand))
    for ia in cand:
        row = []
        for ib in cand:
            row.append("   —" if ia == ib else f"{rms(ml, ia, ib):8.2f}")
        print(f"{ia:>4} " + " ".join(f"{r:>8}" for r in row))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()

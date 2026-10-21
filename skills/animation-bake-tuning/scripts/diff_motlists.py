#!/usr/bin/env python3
"""Semantic per-slot diff between two motlists (layout-independent): names, frame counts,
every curve's keys and values.

Why semantic, not byte ranges: rebuilders append new blobs and repoint slots, so "next slot
start" moves between versions — using it as a blob length reads across into other blobs and
invents differences. Only the parsed result is layout-independent.

PAID-FOR TRAPS:
- Compare curves keyed by BONE HASH, not by bone-name mapping: the name mapping depends on
  which slot's skeleton table parses, and cross-file mapping differences produced 139 phantom
  "changed" slots once.
- Normalize NaN ("nan" if v != v): NaN != NaN makes identical data compare unequal — the same
  139-slot phantom in a second flavor.

Usage: python diff_motlists.py <a.motlist> <b.motlist>
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from motlist_lib import ML, skeleton  # noqa: E402


def digest(path):
    ml = ML(path)
    out = {}
    for i in range(len(ml.starts)):
        if not ml.is_motion(i):
            out[i] = None
            continue
        nf = ml.frames(i)
        try:
            h2 = {h: b["name"] for h, b in skeleton(ml.data, ml.starts[i]).items()}
        except Exception:
            h2 = {}
        curves = []
        for t_hash, kinds in ml.curves(i).items():
            for kind, (times, vals) in kinds.items():
                # NaN normalization — see module docstring
                vals = tuple("nan" if v != v else round(v, 7) for v in vals)
                curves.append((t_hash, kind, tuple(times), vals))
        out[i] = (ml.name(i), nf, tuple(sorted(curves)), h2)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    a = ap.parse_args()
    da, db = digest(a.a), digest(a.b)
    print(f"A = {a.a}  ({Path(a.a).stat().st_size:,} B)")
    print(f"B = {a.b}  ({Path(a.b).stat().st_size:,} B)")
    if len(da) != len(db):
        print("!! 槽位数不同")
    diff = [i for i in sorted(set(da) | set(db)) if da.get(i) != db.get(i)]
    print(f"\n语义不同的槽（{len(diff)} 个）：")
    for i in diff:
        x, y = da.get(i), db.get(i)
        if x is None or y is None:
            print(f"  槽{i:>3}: 一方为空  A={x is not None} B={y is not None}")
            continue
        detail = []
        if x[0] != y[0]:
            detail.append(f"名字 {x[0]!r}→{y[0]!r}")
        if x[1] != y[1]:
            detail.append(f"帧数 {x[1]}→{y[1]}")
        ca = dict(((h, k), (t, v)) for h, k, t, v in x[2])
        cb = dict(((h, k), (t, v)) for h, k, t, v in y[2])
        only_a = sorted(set(ca) - set(cb))
        only_b = sorted(set(cb) - set(ca))
        changed = [k for k in sorted(set(ca) & set(cb)) if ca[k] != cb[k]]

        def nm(h):
            return f"{x[3].get(h) or y[3].get(h) or ('h%08x' % h)}"
        if only_a:
            detail.append(f"A 独有 {len(only_a)} 条曲线（{nm(only_a[0][0])}/{only_a[0][1]}）")
        if only_b:
            detail.append(f"B 独有 {len(only_b)} 条曲线（{nm(only_b[0][0])}/{only_b[0][1]}）")
        if changed:
            k = changed[0]
            ta, tb = ca[k][0], cb[k][0]
            detail.append(f"值不同 {len(changed)} 条（如 {nm(k[0])}/{k[1]}：键数 {len(ta)}→{len(tb)}）")
        print(f"  槽{i:>3}: " + ("；".join(detail) if detail else "仅内部指针/填充不同"))
    print(f"\n相同槽数：{len(da) - len(diff)} / {len(da)}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()

#!/usr/bin/env python3
"""Full-slot speed scan: root net XZ displacement / frame count, ALL layouts included.

The one rotation-independent scan: T curves are plain float3 even on quantized slots, so this
works on every slot and bands the candidates by locomotion speed (idle / walk / run / sprint).
In one investigation this collapsed a 14-slot candidate list to a single slot.

Speed uses fps=60 by default — re-verify for your asset (the timebase is engine/build specific).

Usage: python scan_speeds.py --motlist <file> [--min-speed 2.5]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from motlist_lib import ML  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--motlist", required=True)
    ap.add_argument("--min-speed", type=float, default=2.5)
    ap.add_argument("--fps", type=float, default=60.0)
    a = ap.parse_args()
    ml = ML(a.motlist)
    rows = []
    for i in range(len(ml.starts)):
        if not ml.is_motion(i) or ml.frames(i) <= 0:
            continue
        sp = ml.speed(i, a.fps)
        if sp is not None:
            rows.append((sp, i))
    rows.sort(reverse=True)
    print(f"===== {a.motlist} =====")
    print(f"{'槽':>4} {'动作名':<26} {'帧':>5} {'布局':<6} {'速度m/s':>8} {'净位移':>8}")
    for sp, i in rows:
        if sp < a.min_speed:
            continue
        fl = "float" if ml.header_ok(i) else "量化"
        print(f"{i:>4} {ml.name(i):<26} {ml.frames(i):>5} {fl:<6} {sp:>8.2f} {ml.root_net(i):>7.2f}m")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()

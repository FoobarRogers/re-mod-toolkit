#!/usr/bin/env python3
"""Pose-signature scan of loop slots: torso pitch, head pitch, hip proxy, stride, knee bend,
plus an explicit-criteria `--rank`.

Torso pitch is phase-independent: a clip whose torso leans back through the whole cycle can
never look "leaning forward" — mean AND full-cycle range both matter.

PAID-FOR TRAPS (keep them in mind before "improving" the metrics):
- Stride is measured from the engine's own Foot_IK anchor translation (local Z range). The
  first version used a thigh-bone atan2 angle; when the leg lifts near horizontal it crosses
  ±180° and invents a ~350° fake swing. Do not go back to bone angles for stride.
- Hip proxy is Root+Cog+Waist_00 translation Y sum: translation on the pelvis, not rotation.
  The pelvis is a parent bone — a pose can change without any local-rotation difference.
- Knee bend = thigh-vs-shin direction angle (small = straighter legs).
- `--rank` sorts by explicit criteria (each ranked separately, then summed) — a written-down
  judgment, not a fitted score. Write the symptom signature before ranking. And remember what
  a signature can and cannot say: it says "this clip resembles the symptom", never "the engine
  plays this clip during the symptom" — that needs a runtime motion-ID probe.

Bone names below are RE Engine humanoid conventions (Root/Cog/Waist_00/Spine_00/Neck_00/
Head_00/L|R_Arm/L|R_Leg/L|R_Foot_IK); adapt the chain for a different skeleton.

Usage: python scan_pose.py --motlist <file> [--slots 7,8,9] [--rank] [--min-speed 3.0]
"""
import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from motlist_lib import ML, murmur_name, q_from_xyz, qmul, qrot  # noqa: E402

CHAIN = ("Root", "Cog", "Waist_00", "Spine_00", "Neck_00", "Head_00")


def build_hashes():
    extra = []
    for side in ("L", "R"):
        extra += [f"{side}_Arm_00", f"{side}_Arm_01", f"{side}_Arm_02",
                  f"{side}_Leg_00", f"{side}_Leg_01", f"{side}_Leg_02", f"{side}_Foot_IK"]
    return {n: murmur_name(n) for n in CHAIN + tuple(extra)}


H = build_hashes()


def torso_pitch(world_q_spine, world_q_neck):
    """Torso angle vs vertical (deg); +Z component positive = leaning forward."""
    up = qrot(world_q_spine, (0.0, 1.0, 0.0))
    ang = math.degrees(math.acos(max(-1.0, min(1.0, up[1] / (math.sqrt(sum(c * c for c in up)) or 1.0)))))
    return (1.0 if up[2] > 0 else -1.0) * ang


def leg_metrics(rows):
    """Hip/stride/foot/knee proxies — relative comparison only (same skeleton across slots)."""
    def chain_world(row, bones):
        q = (0.0, 0.0, 0.0, 1.0)
        for bn in bones:
            r = row.get(H[bn], {}).get("R")
            q = qmul(q, q_from_xyz(r)) if r else q
        return q

    hips, knees = [], []
    foot_z = {"L": [], "R": []}
    foot_y = {"L": [], "R": []}
    for row in rows:
        hy = 0.0
        for bn in ("Root", "Cog", "Waist_00"):
            t = row.get(H[bn], {}).get("T")
            if t:
                hy += t[1]
        hips.append(hy)
        for side in ("L", "R"):
            t = row.get(H[f"{side}_Foot_IK"], {}).get("T")
            if t:
                foot_z[side].append(t[2])
                foot_y[side].append(t[1])
            q_t = chain_world(row, ["Root", "Cog", "Waist_00", f"{side}_Leg_00"])
            q_s = chain_world(row, ["Root", "Cog", "Waist_00", f"{side}_Leg_00",
                                    f"{side}_Leg_01", f"{side}_Leg_02"])
            thigh = qrot(q_t, (0.0, 1.0, 0.0))
            shin = qrot(q_s, (0.0, 1.0, 0.0))
            n = math.sqrt(sum(c * c for c in thigh)) or 1.0
            m = math.sqrt(sum(c * c for c in shin)) or 1.0
            dot = max(-1.0, min(1.0, sum(x * y for x, y in zip(thigh, shin)) / (n * m)))
            knees.append(math.degrees(math.acos(dot)))

    def rng(v):
        return (max(v) - min(v)) if v else 0.0

    def mid(v):
        return ((max(v) + min(v)) / 2.0) if v else 0.0

    return {"hip_mean": sum(hips) / len(hips), "hip_range": max(hips) - min(hips),
            "stride": max(rng(foot_z["L"]), rng(foot_z["R"])),
            "foot_y": mid(foot_y["L"]), "foot_y_rng": max(rng(foot_y["L"]), rng(foot_y["R"])),
            "knee_mean": sum(knees) / len(knees)}


def analyze(ml, i):
    rows = ml.sampled(i)
    pitches, head_pitches = [], []
    for row in rows:
        q = (0.0, 0.0, 0.0, 1.0)
        qs = {}
        for bn in CHAIN:
            r = row.get(H[bn], {}).get("R")
            q = qmul(q, q_from_xyz(r)) if r else q
            qs[bn] = q
        pitches.append(torso_pitch(qs["Spine_00"], qs["Neck_00"]))
        up = qrot(qs["Head_00"], (0.0, 1.0, 0.0))
        head_pitches.append(math.degrees(math.acos(max(-1.0, min(1.0, up[1])))))
    return {"idx": i, "name": ml.name(i), "frames": ml.frames(i),
            "speed": ml.speed(i), "net_h": ml.root_net(i),
            "pitch_mean": sum(pitches) / len(pitches),
            "pitch_min": min(pitches), "pitch_max": max(pitches),
            "head_mean": sum(head_pitches) / len(head_pitches), **leg_metrics(rows)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--motlist", required=True)
    ap.add_argument("--slots", default="")
    ap.add_argument("--rank", action="store_true",
                    help="rank by upright torso + high hip + small hip bob (smaller sum = more like the signature)")
    ap.add_argument("--min-speed", type=float, default=3.0)
    a = ap.parse_args()
    ml = ML(a.motlist)
    if a.slots:
        cand = [int(x) for x in a.slots.split(",") if x.strip()]
    else:
        cand = [i for i in range(len(ml.starts))
                if ml.is_motion(i) and ml.header_ok(i)
                and ("Loop" in ml.name(i) or ml.name(i).endswith("_Lo"))]

    print(f"===== {a.motlist} =====")
    print(f"{'idx':>4} {'动作名':<24} {'帧':>5} {'速度m/s':>8} | "
          f"{'躯干均值':>8} {'躯干范围':>16} {'头俯仰':>7} | "
          f"{'髋高':>7} {'髋幅':>6} {'跨步':>6} {'膝弯':>6}")
    rows_all = []
    for i in cand:
        if not ml.header_ok(i):
            print(f"{i:>4} {ml.name(i):<24} {ml.frames(i):>5} {'—':>8} | 量化布局，旋转不可读，跳过")
            continue
        r = analyze(ml, i)
        rows_all.append(r)
        sp = f"{r['speed']:.2f}" if r["speed"] else "—"
        print(f"{r['idx']:>4} {r['name']:<24} {r['frames']:>5} {sp:>8} | "
              f"{r['pitch_mean']:>+7.1f}° [{r['pitch_min']:>+6.1f},{r['pitch_max']:>+6.1f}] "
              f"{r['head_mean']:>6.1f}° | "
              f"{r['hip_mean']:>+7.3f} {r['hip_range']:>6.3f} {r['stride']:>6.3f} {r['knee_mean']:>5.1f}°")

    if a.rank:
        pool = [r for r in rows_all if r.get("speed") and r["speed"] >= a.min_speed]
        if len(pool) < 2:
            print(f"\n--rank: fewer than 2 slots at speed >= {a.min_speed} m/s")
            return
        by_pitch = {r["idx"]: n for n, r in enumerate(sorted(pool, key=lambda r: r["pitch_mean"]), 1)}
        by_hip = {r["idx"]: n for n, r in enumerate(sorted(pool, key=lambda r: -r["hip_mean"]), 1)}
        by_bob = {r["idx"]: n for n, r in enumerate(sorted(pool, key=lambda r: r["hip_range"]), 1)}
        rank = sorted(pool, key=lambda r: by_pitch[r["idx"]] + by_hip[r["idx"]] + by_bob[r["idx"]])
        print(f"\n===== 签名排序（速度 ≥ {a.min_speed} m/s，共 {len(pool)} 槽；直立+高髋+小幅）=====")
        for n, r in enumerate(rank, 1):
            tot = by_pitch[r["idx"]] + by_hip[r["idx"]] + by_bob[r["idx"]]
            print(f"{n:>3} 槽{r['idx']:>3} {r['name']:<24} 合计{tot:>3} "
                  f"| 躯干 {r['pitch_mean']:>+7.1f}° 髋高 {r['hip_mean']:>7.3f} 髋幅 {r['hip_range']:>6.3f}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()

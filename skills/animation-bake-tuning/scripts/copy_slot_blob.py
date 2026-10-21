#!/usr/bin/env python3
"""Reuse a clip across slots: copy the WHOLE blob of one slot and repoint another slot at it.

The minimal-surgery pattern for "symptom X is played by slot B, and a healthy clip in slot A
should play there instead". Why whole-blob copy instead of curve-level cross-source rebuild:
the source blob is a proven asset (its header fields, skeleton, per-curve strategies all
already work in game), and copying keeps every internally-referenced structure intact. A
curve-level re-coupling instead re-joins rhythm-critical pairs by hand — an IK target whose
stride rhythm differs from the root translation it rides with reads as per-step dragging.

Self-check is the point: after surgery, every byte except the destination pointer slot and the
appended region must equal the source file, and the reparsed destination slot must equal the
source slot's content. The replaced slot's old blob stays in the file as an orphan (no pointer
references it) so nothing else moves.

The slot-name string travels with the blob — the destination slot will REPORT the source
slot's name. That is expected: names are not parsed at runtime (one project shipped 20
corrupted names and played fine). It doubles as the in-game acceptance signature: a runtime
probe reading the destination's motion ID with the source's name proves the new data is live.

Usage: python copy_slot_blob.py --src <baseline.motlist> --out <new.motlist> \
           --from-slot 7 --to-slot 82 [--expect-frames 51]
"""
import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from motlist_lib import ML  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="baseline motlist (always regenerate from the baseline, never from a previous output)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--from-slot", type=int, required=True, help="slot whose data to copy")
    ap.add_argument("--to-slot", type=int, required=True, help="slot to repoint")
    ap.add_argument("--expect-frames", type=int, default=None, help="assert both slots' frame counts")
    a = ap.parse_args()

    src = Path(a.src).read_bytes()
    ml = ML(a.src)
    pt = struct.unpack_from("<Q", src, 16)[0]
    cnt = struct.unpack_from("<I", src, 48)[0]

    ia, ib = a.from_slot, a.to_slot
    assert ml.is_motion(ia) and ml.is_motion(ib), "槽不存在或魔数不对"
    name_a, name_b = ml.name(ia), ml.name(ib)
    print(f"复制: 槽{ia} {name_a!r} → 槽{ib}（现为 {name_b!r}）")
    assert ia != ib, "源槽与目标槽相同"
    if a.expect_frames is not None:
        assert ml.frames(ia) == ml.frames(ib) == a.expect_frames, \
            f"帧数不符: {ml.frames(ia)}/{ml.frames(ib)}，期望 {a.expect_frames}"

    # copy range = from-slot start to the next bigger slot start (blob + tail padding;
    # all internal pointers are slot-relative so a copy is self-contained)
    bigger = sorted(x for x in set(ml.starts) if x and x > ml.starts[ia])
    boundary = bigger[0] if bigger else len(src)
    blob = src[ml.starts[ia]:boundary]
    assert len(blob) > 0x1000 and len(blob) % 4 == 0, f"blob 大小异常: {len(blob)}"

    out = bytearray(src)
    while len(out) % 16:
        out.append(0)
    new_off = len(out)
    out.extend(blob)
    struct.pack_into("<Q", out, pt + 8 * ib, new_off)

    # self-check 1: every byte outside the pointer slot + appended region is unchanged
    ptr_lo, ptr_hi = pt + 8 * ib, pt + 8 * ib + 8
    bad = [i for i in range(len(src)) if out[i] != src[i] and not (ptr_lo <= i < ptr_hi)]
    assert not bad, f"意外字节变动 {len(bad)} 处，首处 {bad[0]:#x}"

    # self-check 2: reparsed destination slot equals the source slot's content
    pt2 = struct.unpack_from("<Q", out, 16)[0]
    starts2 = list(struct.unpack_from("<" + "Q" * cnt, out, pt2))
    assert starts2[ib] == new_off, "槽指针未生效"
    ml2 = ML.from_bytes(bytes(out))
    assert ml2.name(ib) == name_a, "目标槽名字未随 blob 带过去"
    assert ml2.frames(ib) == ml.frames(ia), "目标槽帧数不对"
    assert bytes(out[new_off:]) == blob, "追加区内容与源 blob 不一致"

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_bytes(bytes(out))
    print(f"  blob [{ml.starts[ia]:#x}, {boundary:#x}) {len(blob):,} B → {new_off:#x}；"
          f"槽{ib} 指针 {ml.starts[ib]:#x} → {new_off:#x}（旧 blob 成为孤儿数据，保留未动）")
    print(f"  字节差异: 仅指针槽位 {ptr_lo:#x} 的 8 字节 + 追加区 ✓")
    print(f"  实机验收签名: 探针读到 id=<运行时 id of 槽{ib}> + name={name_a!r} = 新数据生效。")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()

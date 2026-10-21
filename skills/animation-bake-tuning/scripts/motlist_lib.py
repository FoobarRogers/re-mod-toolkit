#!/usr/bin/env python3
"""Parsing library for RE Engine MOT/MOTLIST (.528/.495) — the base every slot-research
tool builds on. Distilled from one project's working toolchain; the offset table and the
traps below were each paid for in debugging time. Re-verify offsets against your engine build.

Slot header offsets (slot blob starts at `starts[i]`; all pointers are relative to it):

    s+4    'mot ' magic (validated before parsing anything)
    s+12   u32 — 0 in vanilla slots; some rebuilders write the blob length here (semantics unconfirmed)
    s+16   Q   bone-table pointer -> [Q array_off, Q bone_count], then 80-byte records:
               4Q pointers (first = name string), +32 8f bind pose, +64 (u32 index, u32 name-hash)
    s+24   Q   track-table pointer -> 12-byte records (HHII: index, flags, hash, curve-ptr);
               flags: bit1 = T, bit2 = R, bit4 = S; each curve header = 5x u32
               (fmt, key_count, keys_off, values_off, unpack)
    s+56   Q   jmap pointer (u16 string)
    s+88   Q   slot-name string (u16z). NOT parsed at runtime — one project shipped 20 corrupted
               names and played fine. Never use names to infer routing.
    s+96   f   frame count
    s+100  f   blend / loop flag (vanilla transitions -1.0, loops/idle 0.0; semantics unconfirmed)
    s+112  H   bone count;  s+114  H track count;  s+118  H fps-ish field (re-verify before relying)
    keys  = n x u16 timestamps;  values = n x float3
    float-layout curve fmt: T = 0x4000f2, R = 0x4c0112; quantized-layout R = 0x2x1112 family.

TRAP — `tracks()` hard-reads every curve as u16 timestamps + float3 values. For float-layout
slots that is exact. For quantized slots the R curve is garbage (the codec is unsolved there);
T stays plain float3 and readable. Consequences: full-slot *speed* scans work everywhere, but
rotation comparison only works on float-layout slots — gate with `ML.header_ok()`.
"""
import math
import struct
from pathlib import Path


def u16z(data, off):
    end = off
    while end + 2 <= len(data) and data[end:end + 2] != b"\0\0":
        end += 2
    return data[off:end].decode("utf-16le", errors="replace")


def murmur_name(name):
    """murmur3 over UTF-16LE — the hash used for bone names in the skeleton table."""
    data = name.encode("utf-16le")
    h = 0xFFFFFFFF

    def rol(x, n):
        return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF

    for i in range(0, len(data) // 4 * 4, 4):
        k = int.from_bytes(data[i:i + 4], "little")
        k = rol(k * 0xCC9E2D51 & 0xFFFFFFFF, 15) * 0x1B873593 & 0xFFFFFFFF
        h = (rol(h ^ k, 13) * 5 + 0xE6546B64) & 0xFFFFFFFF
    tail = data[len(data) // 4 * 4:]
    if tail:
        k = int.from_bytes(tail, "little")
        h ^= rol(k * 0xCC9E2D51 & 0xFFFFFFFF, 15) * 0x1B873593 & 0xFFFFFFFF
    h ^= len(data)
    h ^= h >> 16
    h = h * 0x85EBCA6B & 0xFFFFFFFF
    h ^= h >> 13
    h = h * 0xC2B2AE35 & 0xFFFFFFFF
    return h ^ (h >> 16)


def skeleton(data, start):
    table = start + struct.unpack_from("<Q", data, start + 16)[0]
    array, count = struct.unpack_from("<QQ", data, table)
    if not (0 < count <= 256):
        raise ValueError(f"bad bone count {count}")  # quantized slot -> header layout differs
    out = {}
    for i in range(count):
        off = start + array + 80 * i
        if off + 80 > len(data):
            raise ValueError("bone record out of file")
        ptrs = struct.unpack_from("<4Q", data, off)
        name = u16z(data, start + ptrs[0]) if ptrs[0] else f"?{i}"
        idx, hv = struct.unpack_from("<2I", data, off + 64)
        out[hv] = {"name": name, "index": idx,
                   "bind": struct.unpack_from("<3f", data, off + 32)}
    return out


def tracks(data, start):
    """All tracks of one slot. See module docstring: R on quantized slots is NOT readable."""
    base = start + struct.unpack_from("<Q", data, start + 24)[0]
    count = struct.unpack_from("<H", data, start + 114)[0]
    res = []
    for i in range(count):
        off = base + 12 * i
        idx, flags, hv, ptr = struct.unpack_from("<HHII", data, off)
        curves = []
        for bit, kind in [(1, "T"), (2, "R"), (4, "S")]:
            if not flags & bit:
                continue
            header = start + ptr
            f, n, keys, values, unpack = struct.unpack_from("<5I", data, header)
            times = struct.unpack("<" + "H" * n, data[start + keys:start + keys + n * 2]) if n else ()
            vals = struct.unpack("<" + "f" * (n * 3), data[start + values:start + values + n * 12]) if n else ()
            curves.append({"kind": kind, "fmt": hex(f), "n": n, "times": times, "vals": vals})
            ptr += 20
        res.append({"index": idx, "flags": flags, "hash": hv, "curves": curves})
    return res


# ---- quaternion helpers (rotation curves store xyz; w is reconstructed) ----

def q_from_xyz(v):
    x, y, z = v
    w2 = 1.0 - (x * x + y * y + z * z)
    return (x, y, z, math.sqrt(w2) if w2 > 0 else 0.0)


def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


def qrot(q, v):
    x, y, z, w = q
    vx, vy, vz = v
    tx = 2 * (y * vz - z * vy)
    ty = 2 * (z * vx - x * vz)
    tz = 2 * (x * vy - y * vx)
    return (vx + w * tx + (y * tz - z * ty),
            vy + w * ty + (z * tx - x * tz),
            vz + w * tz + (x * ty - y * tx))


def qang(a, b):
    d = abs(sum(x * y for x, y in zip(a, b)))
    return math.degrees(2.0 * math.acos(min(1.0, d)))


class ML:
    """High-level read view over one motlist file. Slot numbers are file-slot indices
    (0-based storage order); the runtime motion ID is the number inside the motion NAME —
    align the two orderings by name, never by position."""

    def __init__(self, path):
        self.path = Path(path)
        self.data = self.path.read_bytes()
        self.starts = self._parse_starts(self.data)

    @classmethod
    def from_bytes(cls, data):
        obj = cls.__new__(cls)
        obj.path = None
        obj.data = data
        obj.starts = cls._parse_starts(data)
        return obj

    @staticmethod
    def _parse_starts(data):
        pt = struct.unpack_from("<Q", data, 16)[0]
        cnt = struct.unpack_from("<I", data, 48)[0]
        return list(struct.unpack_from("<" + "Q" * cnt, data, pt))

    def is_motion(self, i):
        s = self.starts[i]
        return bool(s) and self.data[s + 4:s + 8] == b"mot "

    def name(self, i):
        s = self.starts[i]
        return u16z(self.data, s + struct.unpack_from("<Q", self.data, s + 88)[0])

    def frames(self, i):
        return int(round(struct.unpack_from("<f", self.data, self.starts[i] + 96)[0]))

    def header_ok(self, i):
        """True = skeleton table parses = float layout (rewritten slot); False = quantized
        layout (vanilla content): R unreadable, T fine. Gate rotation comparisons on this."""
        s = self.starts[i]
        tbl = s + struct.unpack_from("<Q", self.data, s + 16)[0]
        _, count = struct.unpack_from("<QQ", self.data, tbl)
        return 0 < count <= 256

    def curves(self, i):
        """{bone_hash: {kind: (times, vals)}} for one slot."""
        cv = {}
        for t in tracks(self.data, self.starts[i]):
            for c in t["curves"]:
                cv.setdefault(t["hash"], {})[c["kind"]] = (list(c["times"]), list(c["vals"]))
        return cv

    def sampled(self, i, step=1):
        """Per-frame [{bone_hash: {kind: vec}}], nearest key, no interpolation."""
        cv = self.curves(i)
        nf = self.frames(i)
        out = []
        for f in range(0, nf + 1, step):
            row = {}
            for h, kinds in cv.items():
                d = {}
                for kind, (times, vals) in kinds.items():
                    k = 0
                    for j, t in enumerate(times):
                        if t <= f:
                            k = j
                    d[kind] = vals[k * 3:k * 3 + 3]
                row[h] = d
            out.append(row)
        return out

    def root_net(self, i):
        """Root translation net XZ displacement (meters), or None. T is plain float3 on
        every layout, so this works on quantized slots too."""
        rt = self.curves(i).get(murmur_name("Root"), {}).get("T")
        if not rt or len(rt[1]) < 6:  # at least two float3 keys
            return None
        v = rt[1]
        return math.hypot(v[-3] - v[0], v[-1] - v[2])

    def speed(self, i, fps=60.0):
        nf = self.frames(i)
        n = self.root_net(i)
        if n is None or nf <= 0:
            return None
        return n / (nf / fps)  # re-verify the 60 fps assumption for your asset

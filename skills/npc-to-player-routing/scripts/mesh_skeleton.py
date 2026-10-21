#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RE Engine MESH 骨架解析 —— Phase F 底层。

职责（`docs/NPC_TO_PLAYER_CONVERSION_WORKFLOW_v0.2-draft.md` Phase F、
`MESH_LuaBone_DS_Review_2026-09-24.md` §11）：

    MESH 文件 -> { bone_name: LocalTranslation }

本模块只负责"从 mesh 取出骨骼名与 Local Translation"。它不感知
`f_shadow.json`、不计算偏移、不生成 LuaBone JSON —— 偏移计算属于
`luabone_generate.py`。两层必须保持分离。

结构契约（仅对 version 0x014111C0 的 skeleton-carrier mesh 验证过）：

    magic    bytes[0:4] == b"MESH"
    version  u32 @ 0x04
    fileSize u64 @ 0x08            # 必须是 u64，见审查意见 §4.1
    S        u64 @ 0x30            # skeleton 结构起点
    J        u16 @ S               # 关节数
    A        u64 @ S+0x10          # 父节点数组，记录步长 16 字节
    P        u64 @ S+0x18          # 局部矩阵数组起点，记录步长 64 字节
    LocalT   float3 @ P + 64*k + 48
    parent(k) = u32 @ A + 16*k 的高 16 位；低 16 位 == k（自索引校验）

    S+0x20 与 S+0x28 指向的另外两组矩阵是全局量与它的反号版本，
    不是 Local Translation，禁止用于生成 LuaBone offset（审查意见 §2）。

    S+0x20 - P == 64 * J 作为结构不变量参与校验。
    P - A == 16 * J 同样是不变量（父节点数组紧邻矩阵数组）。

name table 定位（审查意见 §6）：不把 `Root\\0Cog\\0` 当作唯一锚点。做法是
扫描全文件中"连续 NUL 分隔 ASCII 名"构成的簇，取满足以下条件的簇：
长度 >= J、且**最后 J 项的首项为 `Root`**。实测该类 mesh 中此类簇唯一，
因此结果可唯一确定；`Root\\0Cog\\0` 仅作为 fallback 提示。

版本策略（审查意见 §5）：0x014111C0 -> SUPPORTED，其他版本一律
MANUAL_REVIEW_REQUIRED，不为"兼容更多版本"把未验证结构纳入自动流程。
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

SUPPORTED_MESH_VERSION = 0x014111C0
MESH_MAGIC = b"MESH"

# 连续出现的 NUL 结尾 ASCII 名（材质名与骨骼名共用同一张表）
_NAME_BYTES = re.compile(rb"[A-Za-z0-9_+\-]{2,63}\x00")

# name table 至少要有的项数（材质名 + 若干骨骼名）
_MIN_NAME_CLUSTER = 5

# 64 字节记录不变量的容差
_ROT_TOL = 1e-3
_ONE_TOL = 1e-6

# 记录不变量允许的失败比例，超过即 STOP
_INVARIANT_FAIL_RATIO = 0.05
_INVARIANT_FAIL_MIN = 2

_JOINT_COUNT_MIN = 2
_JOINT_COUNT_MAX = 4096


class ManualReviewRequired(Exception):
    """命中硬 STOP 条件（审查意见 §12）：不"尽量生成"，直接交回人工。"""


@dataclass
class JointRecord:
    index: int
    name: str
    translation: tuple
    invariants_ok: bool
    parent_index: int = -1
    # 3x3 局部旋转，行主序 9 个 float（记录内左上块）。
    # 仅用于只读诊断（骨架旋转 / 累积世界变换）；**不进入 to_report()**，
    # 以保持已落盘 evidence 与 Phase F 输出契约逐字节稳定。
    rotation: tuple = ()


@dataclass
class MeshSkeleton:
    source: str
    file_size: int
    version: int
    joint_count: int
    matrix_array_offset: int
    name_table_offset: int
    parent_array_offset: int = 0
    material_names: list = field(default_factory=list)
    joints: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def joint_names(self):
        return [j.name for j in self.joints]

    def local_translations(self):
        """{bone_name: (x, y, z)}，保留 mesh 中的原始大小写。"""
        return {j.name: j.translation for j in self.joints}

    def parent_of(self, name):
        """大小写不敏感查父节点名；根节点或未找到返回 None。"""
        hits = [j for j in self.joints if j.name.lower() == name.lower()]
        if len(hits) != 1:
            return None
        p = hits[0].parent_index
        if 0 <= p < self.joint_count:
            return self.joints[p].name
        return None

    def hierarchy_chain(self, name):
        """从该骨一路向上到 Root 的链（含自身）。"""
        hits = [j for j in self.joints if j.name.lower() == name.lower()]
        if len(hits) != 1:
            return None
        out = []
        cur = hits[0]
        seen = set()
        while cur is not None and cur.index not in seen:
            seen.add(cur.index)
            out.append(cur.name)
            p = cur.parent_index
            cur = self.joints[p] if 0 <= p < self.joint_count else None
        return out

    def children_of(self, name):
        hits = [j for j in self.joints if j.name.lower() == name.lower()]
        if len(hits) != 1:
            return None
        i = hits[0].index
        return [j.name for j in self.joints if j.parent_index == i]

    def lookup(self, name):
        """大小写不敏感精确匹配（审查意见 §7）。歧义或多义时拒绝猜测。"""
        hits = [j for j in self.joints if j.name.lower() == name.lower()]
        if len(hits) == 1:
            return hits[0].translation
        if not hits:
            return None
        raise ManualReviewRequired(
            "大小写不敏感匹配出现歧义：%r 命中 %s"
            % (name, [j.name for j in hits])
        )

    def to_report(self):
        return {
            "source": self.source,
            "file_size": self.file_size,
            "mesh_version": "0x%08X" % self.version,
            "joint_count": self.joint_count,
            "matrix_array_offset": self.matrix_array_offset,
            "parent_array_offset": self.parent_array_offset,
            "name_table_offset": self.name_table_offset,
            "material_names": self.material_names,
            "joint_names": self.joint_names,
            "parent_names": [
                (self.joints[j.parent_index].name if 0 <= j.parent_index < self.joint_count else None)
                for j in self.joints
            ],
            "invariant_failures": [j.name for j in self.joints if not j.invariants_ok],
            "warnings": self.warnings,
        }


def _locate_name_table(data, joint_count, source):
    """定位 name table，返回 (整簇, 最后 joint_count 项)。

    验证条件：簇长度 >= J，且最后 J 项的首项为 `Root`。
    """
    clusters = []
    cur = []
    for m in _NAME_BYTES.finditer(data):
        off = m.start()
        if cur and off == cur[-1][0] + len(cur[-1][1]) + 1:
            cur.append((off, m.group()[:-1]))
        else:
            if len(cur) >= _MIN_NAME_CLUSTER:
                clusters.append(cur)
            cur = [(off, m.group()[:-1])]
    if len(cur) >= _MIN_NAME_CLUSTER:
        clusters.append(cur)

    if not clusters:
        raise ManualReviewRequired("%s: 未找到任何连续 ASCII 名簇，无法定位 name table" % source)

    clusters.sort(key=len, reverse=True)
    for cluster in clusters:
        if len(cluster) < joint_count:
            continue
        tail = cluster[len(cluster) - joint_count:]
        if tail[0][1] == b"Root":
            return cluster, tail

    sizes = [len(c) for c in clusters[:5]]
    raise ManualReviewRequired(
        "%s: 没有任何名簇满足『长度 >= J(%d) 且最后 J 项首项为 Root』；"
        "最大簇长度 = %s" % (source, joint_count, sizes)
    )


def parse_mesh_skeleton(data, source="<bytes>", allowed_versions=None):
    """解析 MESH 骨架。

    `allowed_versions` 默认 `None` —— 即只接受生产已验证的
    `SUPPORTED_MESH_VERSION`。研究分支可以显式传入额外版本做只读解析，
    但**不得**用放开后的结果生成生产 LuaBone；生产调用点一律不传该参数。
    """
    size = len(data)
    if size < 0x80:
        raise ManualReviewRequired("%s: 文件过小 (%d 字节)，不是合法 MESH" % (source, size))
    if data[:4] != MESH_MAGIC:
        raise ManualReviewRequired(
            "%s: MESH magic 不匹配（前 4 字节 %r）" % (source, data[:4])
        )

    accepted = (SUPPORTED_MESH_VERSION,) if allowed_versions is None else tuple(allowed_versions)
    version = struct.unpack_from("<I", data, 0x04)[0]
    if version not in accepted:
        raise ManualReviewRequired(
            "%s: MESH version 0x%08X 未经验证，当前只支持 %s"
            % (source, version, ", ".join("0x%08X" % v for v in accepted))
        )

    file_size = struct.unpack_from("<Q", data, 0x08)[0]
    if file_size != size:
        raise ManualReviewRequired(
            "%s: fileSize 字段 %d != 实际长度 %d" % (source, file_size, size)
        )

    S = struct.unpack_from("<Q", data, 0x30)[0]
    if not (0x80 <= S <= size - 16):
        raise ManualReviewRequired("%s: skeleton 结构偏移 S=%d 越界" % (source, S))

    joint_count = struct.unpack_from("<H", data, S)[0]
    if not (_JOINT_COUNT_MIN < joint_count < _JOINT_COUNT_MAX):
        raise ManualReviewRequired("%s: 关节数 J=%d 异常" % (source, joint_count))

    P = struct.unpack_from("<Q", data, S + 0x18)[0]
    if P + 64 * joint_count > size:
        raise ManualReviewRequired(
            "%s: 矩阵数组 P=%d + 64*J=%d 越界（文件 %d）"
            % (source, P, 64 * joint_count, size)
        )
    Q = struct.unpack_from("<Q", data, S + 0x20)[0]
    if Q - P != 64 * joint_count:
        raise ManualReviewRequired(
            "%s: 结构不变量 (S+0x20 - P) == 64*J 不成立：%d - %d != %d"
            % (source, Q, P, 64 * joint_count)
        )

    A = struct.unpack_from("<Q", data, S + 0x10)[0]
    if A + 16 * joint_count > size:
        raise ManualReviewRequired(
            "%s: 父节点数组 A=%d + 16*J=%d 越界（文件 %d）"
            % (source, A, 16 * joint_count, size)
        )
    if P - A != 16 * joint_count:
        raise ManualReviewRequired(
            "%s: 结构不变量 (P - A) == 16*J 不成立：%d - %d != %d"
            % (source, P - A, A, 16 * joint_count)
        )

    parents = []
    for k in range(joint_count):
        col0 = struct.unpack_from("<I", data, A + 16 * k)[0]
        self_index = col0 & 0xFFFF
        if self_index != k:
            raise ManualReviewRequired(
                "%s: 父节点数组自索引不一致 @%d：低 16 位 = %d" % (source, k, self_index)
            )
        parents.append(col0 >> 16)

    cluster, tail = _locate_name_table(data, joint_count, source)

    failures = []
    joints = []
    for k, (_, raw_name) in enumerate(tail):
        f = struct.unpack_from("<16f", data, P + 64 * k)
        r0 = f[0] ** 2 + f[1] ** 2 + f[2] ** 2
        r1 = f[4] ** 2 + f[5] ** 2 + f[6] ** 2
        r2 = f[8] ** 2 + f[9] ** 2 + f[10] ** 2
        ok = (
            abs(r0 - 1.0) < _ROT_TOL
            and abs(r1 - 1.0) < _ROT_TOL
            and abs(r2 - 1.0) < _ROT_TOL
            and abs(f[3]) < _ROT_TOL
            and abs(f[7]) < _ROT_TOL
            and abs(f[11]) < _ROT_TOL
            and abs(f[15] - 1.0) < _ONE_TOL
        )
        name = raw_name.decode("ascii")
        if not ok:
            failures.append(name)
        rot3 = (f[0], f[1], f[2], f[4], f[5], f[6], f[8], f[9], f[10])
        joints.append(JointRecord(k, name, (f[12], f[13], f[14]), ok, parents[k], rot3))

    tolerated = max(_INVARIANT_FAIL_MIN, int(joint_count * _INVARIANT_FAIL_RATIO))
    if len(failures) > tolerated:
        raise ManualReviewRequired(
            "%s: 64 字节记录不变量失败 %d/%d 根（容差 %d）：%s"
            % (source, len(failures), joint_count, tolerated, failures[:10])
        )

    warnings = []
    if failures:
        warnings.append("记录不变量失败（在容差内）：%s" % failures)

    lower = {}
    for j in joints:
        lower.setdefault(j.name.lower(), []).append(j.name)
    dupes = {k: v for k, v in lower.items() if len(v) > 1}
    if dupes:
        warnings.append("大小写不敏感重名（Phase F 匹配会歧义）：%s" % dupes)

    material_names = [n.decode("ascii") for _, n in cluster[: len(cluster) - joint_count]]

    return MeshSkeleton(
        source=source,
        file_size=size,
        version=version,
        joint_count=joint_count,
        matrix_array_offset=P,
        name_table_offset=cluster[0][0],
        parent_array_offset=A,
        material_names=material_names,
        joints=joints,
        warnings=warnings,
    )


def load_mesh_skeleton(path, allowed_versions=None):
    p = Path(path)
    return parse_mesh_skeleton(p.read_bytes(), source=str(p), allowed_versions=allowed_versions)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="解析 RE Engine MESH 的骨架与 Local Translation（Phase F 底层）"
    )
    ap.add_argument("mesh", help="目标 .mesh.<version> 文件")
    ap.add_argument("--report", help="把完整解析报告写成 JSON")
    args = ap.parse_args(argv)

    try:
        sk = load_mesh_skeleton(args.mesh)
    except ManualReviewRequired as exc:
        print("MANUAL_REVIEW_REQUIRED")
        print("  " + str(exc))
        return 2

    print("MESH 解析 PASS")
    print("  source        : %s" % sk.source)
    print("  version       : 0x%08X" % sk.version)
    print("  size          : %d" % sk.file_size)
    print("  joint_count J : %d" % sk.joint_count)
    print("  matrix array P: 0x%x" % sk.matrix_array_offset)
    print("  name table    : 0x%x" % sk.name_table_offset)
    print("  materials     : %s" % sk.material_names)
    print("  first 8 bones : %s" % sk.joint_names[:8])
    print("  last 8 bones  : %s" % sk.joint_names[-8:])
    for w in sk.warnings:
        print("  WARNING: %s" % w)

    if args.report:
        out = Path(args.report)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(sk.to_report(), indent=2, ensure_ascii=False) + "\n")
        print("  report        : %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

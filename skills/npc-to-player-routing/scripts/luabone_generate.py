#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LuaBone custom JSON 生成 —— Phase F 上层。

职责（`MESH_LuaBone_DS_Review_2026-09-24.md` §7、§11）：

    mesh_skeleton(bone -> LocalT)  +  f_shadow.json(bone -> LocalT)
        ->  LuaBone custom JSON(bone -> offset)

生成公式：

    LuaBoneOffset(bone) = targetMesh.LocalT(bone) - f_shadow.LocalT(bone)

    xyz 直接对应 xyz；不许轴交换，不许符号翻转；mesh 侧按 float32 读出后，
    在 Python float（double）精度下相减。

匹配规则（审查意见 §7）：

    case-insensitive exact-name match；显式 alias 表可留但需人工确认；
    禁止 fuzzy matching。NPC 与 Player 的骨骼顺序可以不同，所以只能按骨名
    匹配，不能按索引对应。

缺失策略（审查意见 §8）：

    missing_policy = golden_compatible_zero

    一律表述为"Golden 兼容的零值约定"，**不是** RE Engine 通用不变量。
    目前只有 J017 一个成品样本支持它；在第二个已有正确 LuaBone JSON 的成品
    复现通过之前，不得升级为稳定规则。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mesh_skeleton import ManualReviewRequired, load_mesh_skeleton  # noqa: E402

# 输出键集中额外固定存在的键。它们**不在** f_shadow.json 里，在 J017 Golden
# 的成品 JSON 中以 0.0 出现。来源为单样本观察，见 missing_policy 说明。
EXTRA_KEYS = (
    "Root",
    "Cog",
    "Face_Parts",
    "L_Foot_IK",
    "R_Foot_IK",
    "LookAt",
    "PL_Cam",
)

MISSING_POLICY = "golden_compatible_zero"
MISSING_POLICY_NOTE = (
    "单样本约定：来自 J017 GoldenCandidate 的成品 LuaBone JSON。"
    "缺任一侧（mesh 或 f_shadow）即输出 0.0。"
    "尚无第二个独立成品复现，不得当作 RE Engine 通用不变量。"
)

# 输出格式与 J017 Golden 成品逐字节对齐
JSON_INDENT = 4
JSON_SORT_KEYS = True
JSON_TRAILING_NEWLINE = False


def _zero():
    return {"x": 0.0, "y": 0.0, "z": 0.0}


def generate(mesh_path, shadow_path, *, allow_missing_target=False, allowed_versions=None):
    """生成 LuaBone offsets。

    `allowed_versions` 默认 `None` —— 只接受生产已验证的 `SUPPORTED_MESH_VERSION`。
    研究分支（`TODO_WORKFLOW_Taxonomy_Runtime_Validation` TODO 08）可显式传入额外版本，
    **前提是该版本的结构契约已有可重放证据**；这**不构成**把它加入生产支持的依据，
    生产调用点一律不传该参数。
    """
    sk = load_mesh_skeleton(mesh_path, allowed_versions=allowed_versions)
    shadow = json.loads(Path(shadow_path).read_text(encoding="utf-8"))

    keys = sorted(set(shadow) | set(EXTRA_KEYS))
    result = {}
    matched, aliases, missing_target = [], [], []
    no_base, dropped = [], []
    zero_keys = []

    for name in keys:
        target = sk.lookup(name)                      # case-insensitive
        base = shadow.get(name)                       # f_shadow 是精确键

        if target is not None and base is not None:
            matched.append(name)
            hit = [j.name for j in sk.joints if j.name.lower() == name.lower()][0]
            if hit != name:
                aliases.append({"f_shadow_key": name, "mesh_bone": hit,
                                "reason": "case_insensitive"})
            result[name] = {
                "x": target[0] - base["x"],
                "y": target[1] - base["y"],
                "z": target[2] - base["z"],
            }
            continue

        result[name] = _zero()
        zero_keys.append(name)

        if base is not None:
            # f_shadow 有、mesh 无 -> 关键骨缺失，由调用方决定是否 STOP
            missing_target.append(name)
            continue

        # f_shadow 无 base 的键（含 EXTRA_KEYS）-> 按 golden_compatible_zero 置 0。
        # 这里必须区分两种来源不同的情况，否则报告会把「mesh 里有骨、值被丢弃」
        # 说成「本来就不存在」，直接误导后续 NPC 的审查：
        #   mesh_present=False -> 该键两侧都无，置 0 无信息损失
        #   mesh_present=True  -> mesh 有该骨，其 LocalT 被丢弃（实机观察重点）
        entry = {"key": name, "mesh_present": target is not None}
        if target is not None:
            entry["mesh_local_translation"] = {
                "x": target[0], "y": target[1], "z": target[2]}
            nonzero = any(abs(v) > 1e-12 for v in target)
            entry["mesh_value_nonzero"] = nonzero
            if nonzero:
                dropped.append(name)
        no_base.append(entry)

    max_abs = 0.0
    for name in matched:
        v = result[name]
        max_abs = max(max_abs, abs(v["x"]), abs(v["y"]), abs(v["z"]))

    mesh_only = sorted(
        set(sk.joint_names) - {j for j in sk.joint_names
                               if j.lower() in {k.lower() for k in keys}},
    )

    report = {
        "mesh": str(mesh_path),
        "mesh_version": "0x%08X" % sk.version,
        "mesh_joint_count": sk.joint_count,
        "shadow": str(shadow_path),
        "shadow_key_count": len(shadow),
        "output_key_count": len(result),
        "missing_policy": MISSING_POLICY,
        "missing_policy_note": MISSING_POLICY_NOTE,
        "matched_count": len(matched),
        "matched_bones": matched,
        "aliases_used": aliases,
        "missing_target_bones": missing_target,
        "keys_without_f_shadow_base": no_base,
        "dropped_mesh_values": dropped,
        "zero_valued_keys": zero_keys,
        "mesh_only_bones_not_in_output": mesh_only,
        "mesh_only_bone_count": len(mesh_only),
        "max_abs_offset": max_abs,
        "warnings": sk.warnings,
    }

    if missing_target and not allow_missing_target:
        raise ManualReviewRequired(
            "f_shadow 关键骨在 mesh 中缺失（%d 根）：%s  ——  按 workflow §Phase F "
            "『关键骨匹配不完整时停止』，不生成 LuaBone JSON"
            % (len(missing_target), missing_target[:10])
        )

    return result, report


def dump_json(obj, path):
    text = json.dumps(obj, indent=JSON_INDENT, sort_keys=JSON_SORT_KEYS)
    if JSON_TRAILING_NEWLINE:
        text += "\n"
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    # newline='\n' 是硬要求：Golden 成品用 LF，Windows 默认会把 \n 写成 \r\n，
    # 会在逐字节回归里直接暴露。
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return p


def main(argv=None):
    ap = argparse.ArgumentParser(description="生成 LuaBone custom JSON（Phase F）")
    ap.add_argument("--mesh", required=True, help="skeleton-carrier mesh")
    ap.add_argument("--shadow", default="base/f_shadow.json", help="LuaBone base JSON")
    ap.add_argument("--out", required=True, help="输出的 LuaBone custom JSON")
    ap.add_argument("--report", help="validation report 输出路径")
    ap.add_argument("--compare", help="与给定 JSON 做逐字节比对（回归 oracle 用）")
    ap.add_argument("--allow-missing-target", action="store_true",
                    help="允许 f_shadow 关键骨缺失（默认不允许，缺失即 STOP）")
    args = ap.parse_args(argv)

    try:
        result, report = generate(
            args.mesh, args.shadow, allow_missing_target=args.allow_missing_target
        )
    except ManualReviewRequired as exc:
        print("MANUAL_REVIEW_REQUIRED")
        print("  " + str(exc))
        return 2

    out = dump_json(result, args.out)

    print("LuaBone 生成 PASS")
    print("  mesh          : %s" % args.mesh)
    print("  shadow        : %s (%d keys)" % (args.shadow, report["shadow_key_count"]))
    print("  output        : %s (%d keys)" % (out, report["output_key_count"]))
    print("  matched       : %d" % report["matched_count"])
    print("  aliases used  : %d %s" % (
        len(report["aliases_used"]),
        [a["f_shadow_key"] for a in report["aliases_used"]],
    ))
    print("  missing target: %d" % len(report["missing_target_bones"]))
    print("  no-base keys  : %d  (mesh_present=%d, mesh value dropped=%d)"
          % (len(report["keys_without_f_shadow_base"]),
             sum(1 for e in report["keys_without_f_shadow_base"] if e["mesh_present"]),
             len(report["dropped_mesh_values"])))
    for e in report["keys_without_f_shadow_base"]:
        if e["mesh_present"]:
            t = e["mesh_local_translation"]
            print("      %-12s mesh LocalT=(%.9g, %.9g, %.9g) nonzero=%s"
                  % (e["key"], t["x"], t["y"], t["z"], e["mesh_value_nonzero"]))
    print("  mesh-only     : %d bones not in output key set"
          % report["mesh_only_bone_count"])
    print("  max abs offset: %.9g" % report["max_abs_offset"])
    for w in report["warnings"]:
        print("  WARNING: %s" % w)

    if args.report:
        rp = Path(args.report)
        rp.parent.mkdir(parents=True, exist_ok=True)
        with open(rp, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        print("  report        : %s" % rp)

    if args.compare:
        a = Path(args.compare).read_bytes()
        b = out.read_bytes()
        if a == b:
            print("  回归比对      : BYTE-IDENTICAL  (%d bytes)" % len(b))
            return 0
        print("  回归比对      : MISMATCH")
        print("    expected %d bytes, got %d bytes" % (len(a), len(b)))
        for i, (x, y) in enumerate(zip(a, b)):
            if x != y:
                print("    first diff @ byte %d: expected %r got %r" % (i, bytes([x]), bytes([y])))
                print("    expected ctx: %r" % a[max(0, i - 40):i + 40])
                print("    actual   ctx: %r" % b[max(0, i - 40):i + 40])
                break
        return 3

    return 0


if __name__ == "__main__":
    sys.exit(main())

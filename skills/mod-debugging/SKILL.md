---
name: mod-debugging
description: "分析日志类证据——re2_framework_log.txt、Mod 日志或其他日志文件：先在本地筛出需要的条目及其上下少量条目，再分析这些条目。用于 hook 未命中、重载顺序、重复报错、时序与性能等必须还原运行过程才能定位的问题。若一条 Lua 报错看脚本与错误消息即可定因（弹窗里的 file:line、语法或沙箱能力不符），那属于 reframework-lua-development。纯模型、材质等资源问题不要使用。Diagnose from log evidence — filter to the relevant entries plus a little surrounding context before analysing. For failures that require the runtime timeline; not for load-time errors visible in the script itself. Route asset-only failures elsewhere."
---

# Mod Debugging

Diagnose from bounded log evidence. Do not load a large log wholesale into context.

## Scope the evidence

Identify the affected module, reproduction action, approximate time, REFramework build, script version, and whether Reset Script or a map/player transition occurred. Preserve the original log and work from a filtered summary.

For a large text log, use `scripts/summarize_reframework_log.py` or an equivalent project tool:

```bash
python3 scripts/summarize_reframework_log.py re2_framework_log.txt \
  --module ArmorVariantManager \
  --output tmp/out/avm-log-summary.md
```

Inspect the filtered report and only the smallest surrounding regions needed to validate a hypothesis.

## Classify the failure

Separate:

- Lua syntax or load failure;
- stack traceback, `nil`, invalid managed object, or stale cache;
- hook lookup, overload, instance, timing, or return-value error;
- duplicate callback or Reset Script state;
- configuration parse, migration, path, or permission error;
- runaway logging or repeated high-frequency failure;
- evidence that the actual problem is a native resource, loader, or visual issue.

A Lua traceback whose cause is visible in the script itself — an unsupported sandbox facility, a load-order contract violation — belongs to `reframework-lua-development`. Keep this skill for failures that require the runtime timeline.

Absence of an error line is not proof that the feature ran. Look for positive evidence such as script load, hook registration, state transition, expected path resolution, or a bounded diagnostic marker.

## Form and test one hypothesis

State the evidence, inferred cause, contradicting evidence, and smallest discriminating test. Prefer a diagnostic that can prove or disprove one boundary: loaded versus not loaded, object present versus absent, hook called versus never called, callback duplicated versus single, config read versus defaulted.

Avoid adding permanent per-frame logs. Gate or throttle temporary instrumentation, and remove or disable it in the delivered build.

When logs point to mesh, material, PFB, MOTLIST, loose-file cache, resource paths, or another native layer, hand off to `reengine-asset-diagnosis`. When the defect is mainly visual, use `mod-visual-validation` for matched evidence.

## Report the diagnosis

Return:

- reproduction scope and relevant time/module;
- decisive log excerpts or grouped signatures;
- confirmed facts versus inference;
- most likely cause and alternatives;
- minimal next test or fix location;
- whether more instrumentation is needed;
- any limitations caused by missing or truncated evidence.

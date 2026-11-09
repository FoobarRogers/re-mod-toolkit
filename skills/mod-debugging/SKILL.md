---
name: mod-debugging
description: "分析日志类证据——re2_framework_log.txt、Mod 日志或其他日志文件：先在本地筛出需要的条目及其上下少量条目，再分析这些条目。用于 hook 未命中、重载顺序、重复报错、时序与性能等必须还原运行过程才能定位的问题。若一条 Lua 报错看脚本与错误消息即可定因（弹窗里的 file:line、语法或沙箱能力不符），那属于 reframework-lua-development。纯模型、材质等资源问题不要使用。Diagnose from log evidence — filter to the relevant entries plus a little surrounding context before analysing. For failures that require the runtime timeline; not for load-time errors visible in the script itself. Route asset-only failures elsewhere; also use for suspected mod-related silent crashes with no log trail — designing targeted capture for a next occurrence, correlating crash-time evidence (faulting module, timing, mod lifecycle), or preparing a player evidence-collection package. 中文触发: 闪退无日志、取证"
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

Avoid adding permanent per-frame logs. Gate or throttle temporary instrumentation, and remove or disable it in the delivered build. For file-writing instrumentation:

- place the write after the event filter, not at hook entry — a shared GUI method can fire hundreds of times per second across unrelated widgets, and a DOCLOSE-family storm turns a naive hook-entry write into disk-storming;
- wrap diagnostic helpers in pcall — including argument expressions evaluated before the call — so their own Lua errors never propagate into the flow under test; near a crash edge, log values already in hand instead of re-querying live objects to complete the record;
- capture the original error stack before the stack unwinds (an xpcall message handler) — a debug.traceback() taken after pcall returns reflects the handling site, not the fault site;
- mark the diagnostic block, or gate it behind one toggleable helper module, with a removal marker so diff-review and cleanup stay mechanical.

When the failure is a silent crash (process gone, no script log trail), switch from log diagnosis to forensic capture. Choose layers by the current evidence gap — each answers a different question, and the open question decides which to deploy:

- lifecycle trace (event-driven, appended, zero per-frame IO) — where was the mod in its lifecycle when it died;
- first-error blackbox (err + traceback + version + live state; throttle by an explicit definition of "first" — per session, per reproduction, or per error signature) — what did the script itself report;
- framework log — native exceptions with call stacks, when the build and failure path are ones it captures;
- OS crash record (Windows Event Log) — did the process actually die, and where.

Two attribution traps: a mod-induced crash often faults in game code or ntdll, not the mod DLL — the faulting module correlates the crash with a time and a module, it does not establish root cause or exonerate the mod; and an exception handled without terminating the process does not necessarily produce an automatic crash report — absence of a WER record does not establish that no exception or process failure occurred. When asking players to collect evidence, identify which files are overwritten or rotated at session start and have those copied before the game restarts.

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

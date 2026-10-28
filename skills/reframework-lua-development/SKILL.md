---
name: reframework-lua-development
description: "开发或审查 REFramework Lua Mod，处理运行生命周期、Hook、原生流程介入（原生弹窗、列表适配、任务/网络状态机）、配置、UI 分离和脚本重载，包括玩家扫描、外观/变身控制、LuaBone 与自定义骨骼控制器；也用于修复脚本自身报出的错误——ScriptRunner 弹窗、红字、语法与加载失败、沙箱能力不符、加载时机契约。从零新建脚本、修改或修复 Lua 功能、或接手他人既有 mod 二次开发时使用；不用于原生 DLL 或纯资源修改；必须还原运行过程才能定位的故障诊断（hook 未命中、重载顺序、重复报错、性能与时序）不在本 skill 主责范围内，证据充分后实施与验证 Lua 修复仍属本 skill。Develop or review REFramework Lua mods with correct lifecycle, hooks, native-flow integration, configuration, UI separation, and reload behavior, including player scanning, appearance or transformation control, LuaBone, and custom bone controllers; use when creating a script from scratch, modifying or fixing Lua features, or taking over an existing mod authored by someone else; also fix errors the script itself raises. Not for native DLL or asset-only work. Runtime-incident reconstruction (hook never fired, reload ordering, repeated errors, timing or performance) is outside this skill's primary scope; use this skill to implement and validate Lua changes once sufficient evidence is available."
---

# REFramework Lua Development

Use the REFramework version declared by the project. Prefer the project's verified code, type information, and runtime evidence over old tutorials or remembered APIs. For nontrivial subsystems — player scanning, caching, per-frame state maintenance — look for an already-verified in-project implementation to use as a reference, after checking that its assumptions match the current task, before inventing a new design.

## Establish the runtime contract

Before editing, identify:

- the supported REFramework build, such as stable or nightly;
- when the script loads and when the target singleton or player object exists;
- the events that invalidate cached managed objects;
- whether the feature runs from a hook, frame callback, UI callback, or explicit action;
- where configuration and runtime data belong.

Do not interpret an unavailable singleton at the title screen as proof that the API is absent. Reacquire objects after load, map, quest, player, or managed-object reconstruction when required.

Check four layers before writing — most load-time failures come from skipping the second:

1. Lua syntax — would standard Lua also reject it?
2. Sandbox — does the target build provide every global and stdlib call it makes?
   `os.execute` runs on the desktop and is `nil` in the game; `arg` does not exist at all; `io.open` on a missing directory returns `nil` silently; `json` exists in game, not in a plain interpreter.
3. Load contract — does every object it touches exist at that lifecycle point?
   An unavailable singleton at the title screen is a timing fact, not a missing API.
4. Managed layer — type, signature, nullability.

Read a load failure by its shape: `attempt to index/call a nil value (global 'X')` or `field 'X' is not callable` usually means the environment does not provide X — check the environment before editing logic. A blanket `pcall` turns that into a silent no-op; guard only the calls that may legitimately fail and keep a diagnostic path.

Read [runtime-and-hooks.md](references/runtime-and-hooks.md) when touching managed objects, hooks, callbacks, caching, or performance. Read [native-integration.md](references/native-integration.md) when the feature calls into, reuses, or takes over native flows — dialogs, lists, quest or network state machines — or when deciding how deep to integrate and how to probe the native contract first. Read [structure-and-delivery.md](references/structure-and-delivery.md) when adding UI, configuration, localization, persistent state, or preparing a test build. Read [sandbox-and-errors.md](references/sandbox-and-errors.md) when the script depends on a global or stdlib call, or when a popup or red error text appears. Read [onboarding-existing-mod.md](references/onboarding-existing-mod.md) before changing a script whose runtime structure and design assumptions have not yet been established in the current task — especially one showing signs of repeated patching — to map its drivers and decide what to keep, remove, or re-baseline.

When writing a script from scratch, or introducing an API call the project has not used yet, load the `reframework-api-reference` skill first and read only the pages its index routes to — do not write API signatures from memory. Edits that rework existing logic, configuration, or strings without new API calls do not need it.

## Player scanning and application

For scripts that discover and mutate players, read [player-lifecycle-and-application.md](references/player-lifecycle-and-application.md) before changing scan frequency, instance caches, or application timing. Separate live actor identity, user intent, instance readiness, and writer timing. Preserve proven CG, manual selection, and multiplayer paths while testing a targeted change.

## Implement the smallest coherent change

Keep game behavior independent from whether the UI is open. Centralize configuration access and display strings. Preserve unknown configuration fields when practical, and supply safe defaults for absent or invalid values.

Validate method signatures and instance types before hooking. Use a pre-hook only for work that must precede the original call, a post-hook when the result or completed state is needed. Verify hook semantics rather than inferring them from method names. When no suitable verified transition hook exists, choose bounded polling at the cadence required by the feature; distinguish lightweight actor-identity checks from full discovery scans. Keep high-frequency callbacks free of file I/O, large traversals, repeated reflection, and noisy logs. Prefer state transitions or explicit events over repeating unchanged work every frame. Budget per-frame work in Lua→native bridge calls (`get_field`, `call`, `get_address`): a frame-callback or hot-hook cadence is set by the game or framework and is not yours to optimize — distinguish that invocation frequency from the frequency of substantive work; where the feature permits, skip unchanged work or run expensive checks less often, without changing required response timing. The number of bridge calls per pass is yours to optimize. See the cost model in `runtime-and-hooks.md`.

Make reset or reload behavior explicit. Avoid duplicated state, callbacks, hooks, or side effects after Reset Script; when a hook cannot be unregistered, do not re-add it — have the hook body read current module state rather than captured stale state. If the framework owns callback cleanup, still reset module-local caches and state safely.

## Verify behavior

Check the task-relevant states, not merely script load:

- title versus loaded save;
- hub versus quest when relevant;
- player or map reconstruction;
- UI open and closed;
- every input device the affected flow supports (keyboard, mouse, gamepad) and rapid repeated confirms;
- coexistence with other mods hooking the same methods or touching the same UI entry points;
- missing, old, and fresh configuration;
- Reset Script or hot reload;
- feature enable, disable, and restoration behavior;
- for changes on a per-frame path, a before/after profile comparison under matching scenario and drawing mode, stating the profiler's timing resolution, sampling method, and any resulting limits on the comparison.

A local interpreter proves logic, not environment: list every non-portable facility the script touches and treat it as unverified until the target build loads it — never report "ran fine locally" as verification. Keep stubs, fake-object harnesses, and self-tests out of the deployed tree, each guarded to exit before touching `sdk`, `re`, or `imgui`.

Keep script-side errors here — a popup, or a traceback whose cause is visible in the script plus the error message, is part of the development loop. Hand off to `mod-debugging` for runtime evidence: logs, missed hooks, reload ordering, repeated framework-level errors, timing and performance. Use `reengine-asset-diagnosis` when the evidence points to mesh, material, PFB, physics, path, or another native resource layer.

Deliver the changed files, concise behavior summary, test steps, expected result, and known limitations. Update project handoff or research notes when the project requires it.

---
name: reframework-api-reference
description: "查证 REFramework 平台 API 的签名与语义时使用——从零编写新 Lua 脚本、新增 sdk. / re. / imgui. / json. / fs. / log. / reframework. 或管理对象方法调用且签名不在现有代码中、API 行为与预期不符需要核对官方文档、需要官方示例片段。参考既有代码做不引入新 API 的局部改动（逻辑、配置、字符串）不需要本 skill；运行过程排查用 mod-debugging，原生资源问题用 reengine-asset-diagnosis。Use when you need authoritative REFramework API signatures or semantics: writing a new Lua script from scratch, adding sdk./re./imgui./json./fs./log./reframework. or managed-object calls not already present in the code, when API behavior contradicts expectations, or when you need official examples. Not needed for small edits to existing code that introduce no new API calls."
---

# REFramework API Reference

Offline verbatim copy of the official REFramework Book (`cursey/reframework-book`, upstream commit `acf44b33`, 2026-03-07) under `references/wiki/`. Treat it as the source of truth for REFramework platform APIs — do not write API signatures from memory.

**License**: the upstream book declares no license. Local reference only — never ship this directory inside a mod package or publish it; cite "REFramework Book" with the upstream link instead of copying its text into deliverables.

## How to use

1. Locate the task in the index below and read only the matching 1–3 files.
2. Never read the whole wiki: it is ~212 KB ≈ 53K tokens; single pages are 0.3–4.5K.
3. The wiki does not document game-specific types (`snow.*` / `via.motion.*` members). Verify those against the game's `il2cpp_dump.json`, `RETypeDefinition`, or the in-game Object Explorer.
4. Priority: project-verified runtime evidence (project docs, handoff) > this wiki > tutorials or memory. The snapshot can lag nightly builds.

## Index

| Task / API | Read (paths relative to this skill) |
| --- | --- |
| Managed objects: fields vs methods, colon sugar, overloads, `get_Item`, `self[i]` | `references/wiki/src/api/types/REManagedObject.md` |
| `sdk.*`: singletons, type lookup, calls, hooks, conversions, instance creation, enums | `references/wiki/src/api/sdk.md` |
| Lifecycle callbacks: `re.on_frame`, `re.on_draw_ui`, `re.on_script_reset`, `re.on_application_entry`, hook helpers | `references/wiki/src/api/re.md` |
| Method arguments and return types (signatures, overloads, container-vs-element returns) | `references/wiki/src/api/general/Notes-on-Method-Arguments.md`, `references/wiki/src/api/general/Notes-on-Return-Types.md` |
| Reflection: `RETypeDefinition`, `REMethodDefinition`, `REField` | `references/wiki/src/api/types/RETypeDefinition.md`, `REMethodDefinition.md`, `REField.md` |
| Components and GameObject: `via.Component`, `get_GameObject`, transforms | `references/wiki/src/api/types/REComponent.md`, `RETransform.md` |
| Containers and value types: `SystemArray`, `VectorXf`, `Quaternion`, `Matrix4x4f`, `ValueType`, `REResource` | `references/wiki/src/api/types/` (files of the same names) |
| Scripting discipline: performance, hook choice, common mistakes | `references/wiki/src/api/general/best-practices.md` |
| Config, files, logging, JSON | `references/wiki/src/api/fs.md`, `log.md`, `json.md` |
| Drawing and UI: `draw.*`, `imgui.*` (incl. table and scroll APIs), imnodes, imguizmo | `references/wiki/src/api/draw.md`, `imgui.md`, `imnodes.md`, `imguizmo.md` |
| Threads | `references/wiki/src/api/thread.md` |
| VR | `references/wiki/src/api/vrmod.md` |
| `reframework.*` global (engine version, plugin info) | `references/wiki/src/api/reframework.md` |
| Inspecting live objects from script (`re.object_explorer` global) | `references/wiki/src/api/object_explorer.md` |
| Copy-paste official snippets and example scripts | `references/wiki/src/examples/Example-Snippets.md`, `Example-Scripts.md` |

Not for pure Lua tasks: `references/wiki/src/api_cs/**` (C# scripting), the tool pages (`bhvt_editor`, `chain_viewer`, the full Object Explorer guide), and VR troubleshooting stay in the book for completeness — consult them only when the task explicitly moves to C# or those tools.

The task-routed table with per-page token sizes, two hard-won managed-object contracts (`self.foo` returns a `REMethodDefinition`, not a Lua function; overloaded methods must go through `self:call("foo(full signature)", ...)` because colon sugar does no overload resolution), and the upstream refresh procedure live in `references/wiki/README.md` — read it when you need those details.

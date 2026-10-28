---
name: mod-version-workflow
description: "管理 Mod 在 test、fix、main、prerelease、release 与 add-on（附加包）之间的版本状态。用于新建或提升版本、变更版本号或分支（如 1.10test1 → 1.11）、固化 prerelease 基线（如 1.11prerelease1）、给功能附加包命名（如 bake1.10-escape）、判断允许执行的 Git 操作，以及记录测试或修复结果；单纯制作压缩包时不要使用。Manage mod version state across test, fix, main, prerelease, release, and add-on work: version numbers, branch changes, prerelease baseline freezing, add-on naming, promotion decisions, allowed Git actions, and accepted or rejected test/fix results."
---

# Mod Version Workflow

Treat version work as a state transition, not as a packaging task.

## Establish the project rules

Read the project's `AGENTS.md`, current handoff, version workflow, and version history only when they exist and are relevant. Treat the project's naming, version increment, branch, and evidence rules as authoritative. Do not invent missing project conventions; state the smallest assumption needed or ask when it changes the result materially.

Identify:

- the last user-validated baseline;
- the current candidate and whether it is `test`, `fix`, `main`, `prerelease`, or `release`;
- the requested transition;
- the evidence required by this project;
- the exact Git or publishing actions the user has authorized.

## Control state transitions

Use these default boundaries when the project does not define stricter ones:

| Current work | Allowed outcome without promotion authority |
| --- | --- |
| experiment / test | working-tree changes, evidence, test package, negative result |
| fix | working-tree changes, evidence, fix package |
| prerelease（基线固化） | only after the user authorizes the freeze: prerelease package frozen into the release folder under a prerelease label（如 `1.11prerelease1`）, baseline registered in the version record; subsequent fix/test continues on it; not a release |
| add-on（功能附加包） | working-tree changes, evidence, add-on package with release-grade acceptance; the baseline version number stays unchanged and the add-on is optional to install |
| accepted test/fix | record acceptance and wait for main promotion authority |
| main | prepare release candidate information and wait for release authority |
| release | only actions explicitly authorized for that release |

Never infer permission to commit, merge, push, tag, publish, or create a release merely because a candidate is complete. A command or natural-language instruction such as “promote this accepted test to main” may grant that specific authority. Release remains a separate transition.

Standard development cycle（user-defined, 2026-10-28）: development runs as `test` against the available reference content when present（基础参考内容）; when a stage is basically complete, the user may request a **prerelease freeze** — package the user-accepted state into the release folder under a prerelease label and register it as the working baseline; newly found issues are then handled as `fix`/`test` work on the prerelease baseline; once the fixes for all listed issues have passed verification, the user may authorize the formal release, built from the approved final source state under the final version label without the prerelease suffix（`1.11prerelease1` → `1.11`）; after release, new repairs are `fix` work on the release baseline, and large changes lead to the next version's release. Both the prerelease freeze and the release are user-authorized transitions; never trigger them on your own.

Treat version numbers and branch names as outputs of this workflow, not separate bookkeeping: moving accepted branch `1.10test1` to `1.11` means this skill owns the new label, the required Git actions, and the acceptance record, then hands the label to `mod-package` as an input.

Feature add-ons（A/B 功能替换包：release 是 A 功能版，add-on 仅含替换为 B 功能的文件，非 Lua mod 常见）carry version labels too, owned by this workflow: an add-on named `<base>-<feature>`（如 `bake2.0-escape`）extends an already-shipped baseline without promoting it. **No ordinal**（user rule, 2026-09-20）: the add-on's content is fully derived from the baseline by an idempotent rebuild, so it always carries the baseline's version — baseline bake2.0 → `bake2.0-escape`, baseline 2.1 → `bake2.1-escape`; never increment a feature ordinal (older `escape1/2/3` labels were the pre-rule artifacts). Folding the feature into the numbered main line is a normal promotion and needs promotion authority. The feature name is chosen with the user; it names the theme of the change, not a fix of the baseline.

Before promoting to main, confirm the candidate identity, user acceptance, required verification, scope of included changes, and treatment of unrelated working-tree changes. Before releasing, confirm the source is the approved main state and no unaccepted test/fix work is included. Before freezing a prerelease, confirm the candidate identity, the user's authorization to freeze it as a working baseline, the included changes, the completed validation, known unresolved issues, and evidence locations, then register the baseline in the project version record.

## Preserve evidence

Keep failed experiments distinguishable from fixes and stable versions. Record what changed, what was tested, the result, and the next state. Do not rewrite an already released artifact in place.

When a repository is dirty, preserve unrelated user changes. Stage or include only the accepted candidate unless the user explicitly broadens the scope.

## Hand off to packaging

Use `mod-package` only after the package type and candidate source are resolved. Packaging may build an artifact; it does not decide that a candidate is accepted or authorized for release.

## Report the decision

Return a compact transition record:

- baseline and candidate;
- current state and requested next state;
- validations found or still missing;
- actions allowed now;
- actions withheld pending authority;
- files or records updated.

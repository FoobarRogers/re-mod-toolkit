---
name: mod-package
description: "制作并校验游戏 Mod 的 test、fix、release 或 add-on（附加包）压缩包。用于生成可分发 ZIP、增量补丁、功能附加包、完整包、清单或哈希；候选版本、版本号和包类型必须先确定，不负责版本验收、晋升或版本号变更。Build and verify test, fix, release, or add-on archives, patches, manifests, and hashes after the candidate, version label, and package type are decided."
---

# Mod Package

Package only the resolved candidate. Do not use packaging success as acceptance, main-promotion, or release authority. Take the version label from the version workflow's decision; this skill never increments version numbers or creates branches or tags.

## Resolve the package contract

Read project-specific packaging, layout, and release instructions when present. Identify:

- package type: `test`, `fix`, `release`, or `add-on`;
- exact source state and version label;
- incremental versus complete contents;
- required archive root layout;
- explicit include set and exclusions;
- output location, naming, manifest, and hash requirements.

Read [package-types.md](references/package-types.md) when the project does not fully define the difference between test/fix and release artifacts.

An `add-on`（功能附加包）is a small **optional feature pack** built on an already-shipped baseline: release-grade acceptance applies, the baseline version number does not move, and the package name carries the feature theme (e.g. `bake1.10-escape1`). Choose `add-on` when the change is a self-contained feature the user may install or skip on top of the baseline — not when it repairs the baseline (`fix`) or experiments toward the next number (`test`). Install notes must state that the add-on and the baseline full package cover the same files, so only one may be active at a time (or the add-on must be ordered after the full package).

**Bundle-grouping field** (Fluffy `NameAsBundle`): the add-on and the baseline release must carry the **same value**, and that value must equal the baseline package `name` **verbatim** — including any descriptive prefix and the version suffix (e.g. `[Gameplay]Feminine Animation Replacer_女性化动作_bake2.1`). A near-miss value (e.g. dropping the descriptive prefix) fails **silently**: Fluffy shows two separate entries instead of one bundle, and nothing errors. Generate both values from one shared template instead of hand-writing either; when the baseline omits the field entirely, its `name` is the group key.

## Build from an explicit file set

Prefer the project's existing build or archive script. Otherwise use `scripts/build_mod_package.py`, which requires explicit relative include paths and rejects path traversal and symlinks.

Example:

```bash
python3 scripts/build_mod_package.py \
  --source /path/to/staging-root \
  --include reframework \
  --include natives \
  --output /path/to/output/mod-test4.zip \
  --label test4
```

Use a staging root whose relative paths already match the install layout. Do not flatten `natives`, `reframework`, `Mods`, or other loader-sensitive directories.

Exclude temporary analysis, caches, logs, editor metadata, old packages, and unrelated working-tree files unless the project explicitly requires them. Never source a release archive from an unreviewed mixture of accepted and experimental files.

## Verify the archive

Reopen the finished ZIP and check:

- expected paths and root folder;
- no duplicate members or traversal paths;
- archive CRC integrity;
- manifest file count, size, and SHA256 values;
- package SHA256 when required;
- absence of temporary, stale, or unrelated files;
- presence of every runtime dependency the package contract requires.

For Lua packages, include the intended autorun and required data/config files. For native resource packages, preserve exact paths, names, and version suffixes. For optional AVM or LuaBone material, include it only when the candidate actually uses it.

## Report delivery

State the package type, source candidate, archive name, included roots, file count, package hash, verification result, install/test steps, and rollback package or baseline. If the output is a test/fix patch or an add-on, do not describe it as a complete release; for an add-on, state which baseline it extends, that the baseline version stays unchanged, and the rollback path (disable the add-on to return to the baseline).

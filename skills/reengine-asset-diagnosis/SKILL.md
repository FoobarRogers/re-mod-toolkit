---
name: reengine-asset-diagnosis
description: 诊断 RE Engine Mod 的 mesh、骨骼、权重、物理、材质、贴图、PFB、路径、缓存、Lua 和可选配置问题；涉及 *.tex.28、*.pfb、*.chain.48、*.mdf2.23、*.mesh.2109148288 等带版本后缀的资源文件、作者自建文件夹经 PFB 引用的额外内容，或外观 Mod 的 LuaBone 骨骼调整时使用。外观发灰、发暗、褪色、远处变暗或模糊、场景相关变色或 FX 材质转换也属于本 skill。修改外观、动画或原生资源文件前使用。Diagnose RE Engine mod problems across assets, paths, cache, Lua, LuaBone, and optional configuration before changing appearance, animation, or native resources; also for washed-out, greyed, darkened, scene-dependent or flattened materials and FX material conversion.
---

# RE Engine Asset Diagnosis

Determine which layer owns the symptom before editing files. LuaBone and Armor Variant Manager are optional branches, not assumptions about every appearance mod.

## Establish a verified baseline

Identify the last package confirmed in game, target character or equipment ID, exact resource path, loader combination, affected scenes, and reproduction steps. Distinguish “files changed on disk” from “the game reloaded and used those files.”

If there is no matched baseline, first create a minimal comparison that can show whether the issue comes from the candidate or from environment, loader, cache, or capture conditions.

## Classify the layer

Read [layer-guide.md](references/layer-guide.md) for symptom-to-evidence routing. Consider:

- geometry, normals, weights, skeleton, bind pose, pivot, or physics;
- MDF, shader parameters, texture channels, mipmaps, compression, or lighting;
- PFB instantiation, component binding, object references, or paths;
- loader order, loose-file behavior, cache, reload, or resource version suffix;
- REFramework Lua runtime behavior;
- optional configuration such as AVM only when the mod exposes compatible components;
- LuaBone only when evidence points to runtime transform or skeleton mapping behavior.

Appearance mods typically ship `*.mesh.2109148288`, `*.tex.28`, `*.mdf2.23`, `*.chain.48`, and `*.pfb` files with version suffixes and no skeleton mesh file; bone and attachment corrections run through LuaBone at runtime. Some authors instead keep resources in author-created folders with non-standard suffixes, referenced by a PFB — treat this extra content as first-class material: load failures are still path, loader, cache, or PFB binding issues, and the same protection rules apply.

Do not use LuaBone to compensate for clear geometry, weight, pivot, material, or texture defects. Do not treat AVM JSON as the underlying mesh or material resource.

## Choose and calibrate a material route

For washed-out, greyed, darkened, scene-dependent or flattened appearance, or a proposed FX conversion, read [FX material workflow](references/fx-material-workflow.md). In that workflow, "FX" means the effect-class master material route that renders stylized colour from a dedicated colour map — not any shader with `Vfx` in its name; the reference defines the verified instance and its compatibility gates. Determine the target from user-selected references, in-game feedback and user preferences; do not prescribe a character's colours as general defaults.

Use existing evidence to choose the smallest useful experiment. Preserve working conventional materials where their response meets the goal; test a representative FX conversion early when stable stylized colour is the priority and the existing lighting response conflicts with it. Do not require exhaustive PBR tuning or conversion of every material. Check actual bindings and reload state before repeatedly recolouring an apparently unchanged result.

## Build a change matrix

Before modifying files, record:

| Layer | Change? | File or path | Evidence and purpose |
| --- | --- | --- | --- |
| mesh / skeleton / weight / physics |  |  |  |
| material / texture |  |  |  |
| PFB / binding |  |  |  |
| path / loader / cache |  |  |  |
| runtime Lua / LuaBone |  |  |  |
| optional configuration / AVM |  |  |  |

Prefer one changed variable per experiment. If three or more layers must change, split the experiment unless they form one inseparable reference chain and document why.

## Protect native resources

Resolve who references a path before moving or renaming it. Preserve file names, platform directories, and version suffixes unless the loader contract requires a change.

Do not make speculative byte patches to mesh, MDF, PFB, MOTLIST, or similar binary resources. Use a verified parser or tool, retain the source artifact and parameters, and record hashes when reproducibility matters.

## Produce a diagnosis packet

Report:

- observed symptom and reproduction scope;
- most likely layer and competing hypotheses;
- supporting and contradicting evidence;
- proposed minimal experiment;
- files expected to change and files intentionally unchanged;
- reload procedure and acceptance evidence;
- rollback path.

Use `mod-visual-validation` for matched screenshot or recording judgments. Use `mod-debugging` for REFramework and Lua log analysis. Package only after the experiment and expected file set are defined.

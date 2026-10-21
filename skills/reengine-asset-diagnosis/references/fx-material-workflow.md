# FX material workflow

## 1. Define the visual target and classify the symptom

Use the original package's in-game appearance as the baseline. Use character designs, user-selected references and explicit user preferences to define the target. A promotional image is a style reference, not proof of how the original package renders.

Separate hue error, insufficient saturation, excessive or insufficient brightness, lost surface separation, distance-dependent changes and scene-dependent changes. The same word, such as washed out, can describe different causes. Do not infer a material's intended colour from its part name or another character's palette.

If one scene is already acceptable and another washes out, preserve the accepted scene as a target relationship. Prioritize the difference in material/scene response before globally repainting source colours. Inspect representative owners and their inputs first; expand to other parts or all source mips only when evidence requires it. Full mip verification belongs to edited textures and implicated distance issues, not every initial colour diagnosis.

Map the reported surface to its mesh material and actual texture slots. Inspect the shader, relevant parameters, texture/channel semantics and clean mip 0 (the highest-resolution level). Check vertex colour, UVs or runtime overrides when the observed evidence warrants them. File presence does not establish that the active material reads it. A named glow material need not own every luminous-looking detail.

## 2. Choose conventional shading or a representative FX trial

In this workflow, FX means a route built on the effect-class master material that renders stylized colour from a dedicated colour map. The verified instance in Monster Hunter Rise / Sunbreak uses `MasterMaterial/Master/Vfx/cm/shader_0004_cm_01_1030.mmtr` with the dedicated colour map on `BaseAlphaMap`; its `VertexAnimMap` binds `systems/rendering/NullWhite.tex`. FX is not judged by a `_FX` texture name, and arbitrary `Vfx` shaders are not interchangeable.

A verified-compatible complete schema means the full shader path, flags, property list, texture slots and related structures, taken from a material instance that already works in the same game at the matching resource version. The converter copies that structure through a parser, keeps the material names and hashes referenced by the target mesh, and adjusts the required texture references. Compatibility has two gates: offline check (the written material re-reads correctly, with valid structure, names, references and resource version) and in-game verification (after a full reload, the target part displays, clips, occludes and animates correctly). With only the offline check passed, call it a compatibility candidate. Never treat one shader path or parameter set as a cross-game template.

Distinguish two operations before choosing an experiment:

- **Isolate original emission:** isolate the active EmissiveMap or intensity contribution while retaining the conventional material, as a single-variable A/B test when emission is a suspected cause; this is an optional check, not a required step of FX conversion. This does not make the surface less affected by scene lighting; reducing fill/emission can instead make dark scenes darker. An atlas-wide emission input is not necessarily an independent energy surface, and intended luminous details may need protection.
- **Compare a complete FX route:** use a verified compatible FX schema and dedicated colour input to replace the conventional material's response to scene lighting, reflection, normals and roughness where it keeps diluting the target colour. This is a material-route comparison, not merely switching off native emission: with `EmissiveMap` off, the surface still follows the conventional route and dark scenes can become even darker, while FX changes the whole material presentation route. Exposure, fog and post-processing may still affect the result. Preserve existing emission on accepted energy/crystal surfaces unless that contribution is itself the problem.

| Evidence and user priority | First useful route |
| --- | --- |
| Source colours are inaccurate but the lighting response is acceptable | Correct the relevant source regions; retain the existing material. |
| Unintended emission, tint or reflection plausibly washes out non-emissive surfaces | Audit the active slots and parameters; isolate a relevant correction. |
| Dynamic specular, normal response or scene lighting is important to the desired surface | Prefer preserving the conventional material's useful response. |
| Stable stylized colour is the priority and conventional response repeatedly conflicts with that goal | Compare one representative FX surface against the baseline. Do not exhaust every PBR parameter first. |
| One surface darkens or changes colour across scenes while neighbouring surfaces meet the target | Inspect that surface's actual route; consider a local FX trial rather than a whole-model conversion. |
| Existing crystals, emission, skin or other surfaces already meet the target | Preserve them unless the user requests a change or new evidence points to them. |

Treat scene dependence as a reason to investigate material response, not proof that FX is the only remedy. Compare source texture, material input and reported scene behaviour before selecting the experiment. Offline inspection can select a route but cannot prove game rendering or acceptance.

Do not make emission-off a mandatory first experiment merely because an EMI map and intensity value exist. Use it when isolating that contribution resolves the current uncertainty. When cross-scene colour stability is the user's priority, a representative conventional/FX comparison may be the first experiment. If the priority is unknown, state this decision point without inventing the user's preference or requiring a sequence of PBR trials before FX.

## 3. Construct a controllable FX candidate

- Preserve clean original textures and their provenance. Inspect ALBD (albedo / base colour; its RGB may already carry authored shading, highlights and seams) and emission sources separately. Select detail sources by their actual content and purpose; do not default to an already blurred derivative.
- Preserve authored shading, seams, gradients, soft edges and part separation while changing the intended colour. Use supported baking where needed; avoid baking an incidental scene colour cast into every surface.
- Reuse a working, compatible FX material's complete schema through a verified parser. Check properties, flags, texture slots, material names/hashes and mesh references; changing only a shader path is insufficient.
- Create a separate FX texture when this isolates the experiment and avoids altering another material's source. Keep the material and new texture together as a complete reference chain.
- Decide alpha from the source and destination shader semantics. The source ALBD's alpha channel may carry packed material data instead of opacity — check how the source material actually uses it before choosing the FX input's alpha; a low source alpha must not make a solid part transparent. Use the verified opaque setup when appropriate; do not use transparency as a generic brightness control or assume a translucent FX/PBR overlay works.
- Preserve authored alpha where it controls required visibility. Keep colour, perceived emission and visibility as separate controls.
- Preserve required container version, dimensions, format, layout and names through the verified tool. Mip numbering follows resolution: mip 0 is the highest-resolution level (the largest image, e.g. 2048×2048), and higher mip numbers are smaller. Rebuild the complete mip chain after changes to mip 0, regenerating the lower-resolution levels from the adjusted source. Filter sRGB colour in linear light; process alpha, masks and normal/data maps according to their semantics rather than applying colour gamma indiscriminately.

## 4. Determine colours from reference, game feedback and user intent

Identify the corresponding surface in the reference, game image and texture atlas. Establish desired hue, brightness, saturation, material quality and relative visual intensity from these sources and the user's preference. Reference images already contain lighting, shadow, exposure and post-processing; do not copy a lit reference pixel into a texture as a fixed RGB target.

Compare the three domains to distinguish source-colour mismatch from shader response, scene lighting or loading problems. Define semantic/UV masks and inspect them before editing. Protect unaffected areas and previously accepted results. Retain useful shading and colour differences between material classes; do not flatten all dark or pale surfaces into one colour.

Record which observation motivated each adjustment. Use texture RGB statistics as reproducibility evidence, not universal targets or proof of screen brightness. Calibrate non-emissive surfaces, intended luminous details and adjacent surfaces to the user's desired relationship.

## 5. Respond to user feedback

| Reported symptom | Check and next useful action |
| --- | --- |
| Hue is wrong | Compare reference, source and game; inspect local colour/tint and environment response before recolouring. |
| Colour is faint but brightness is acceptable | Distinguish saturation loss from washed-out contrast; adjust local hue/chroma while protecting approved brightness and visibility. |
| Intended dark surfaces look grey | Inspect local source/input brightness, contrast and material response. Inspect mip mixing if the issue appears mainly at distance. |
| A surface is too dark or weak relative to accepted luminous surfaces | Resolve its actual owner and input brightness; correct that region without increasing all emission or the whole atlas. |
| Non-emissive surfaces look overbright or self-lit | Separate overbright RGB from excessive material emission; calibrate the implicated region and check the problem scene. |
| Same-colour parts merge or look flat | Check whether source detail, gradients, seams and baked shading survived. Preserve conventional response where dynamic shading is required. |
| Near view is correct but distance changes colour or loses detail | Inspect lower mips, UV padding/bleed, alpha, compression and relevant LOD bindings. |
| Detail is missing even near the surface | Inspect mip 0 (the highest-resolution level) and the original detail source first. If it is already lost, recover a clean source before rebuilding mips. If it is intact, check bindings and screen-scale readability. |
| Repeated edits show little or no expected change | Check installed overrides, active resource binding and complete reload. If binding or load state is still uncertain, temporarily bind a high-contrast diagnostic texture (checkerboard or solid bright colour, correct format, required alpha/clip info) and confirm after a full reload which resource the game actually reads; restore the original texture before continuing aesthetic adjustment. Do not keep blind recolouring. |
| A different map breaks the appearance | Compare the affected route, local input and scene response. Test a material or texture correction supported by evidence; do not attribute all differences to exposure. |
| The problem scene improves but a previously acceptable scene becomes too dark or too bright | Check the candidate's local colour inputs and material multipliers against both scenes; calibrate the useful route without repainting the entire atlas or declaring the trade-off accepted. |

Reuse confirmed binding evidence instead of probing every iteration. A successful earlier edit does not prove every later hot reload completed. Use a full restart when reload completeness is in doubt.

## 6. Verify and stop at the requested scope

Decode the written texture independently; check all mips, dimensions, payload/layout, alpha and colour/detail preservation. Where feasible, preserve untouched compressed blocks in mip 0. Distinguish unchanged intended pixels from neighbouring pixels altered by shared-block compression; lower mips naturally mix boundaries.

Choose error limits by format, scale and content and report observed errors. Investigate failed checks; do not loosen limits merely to make a candidate pass. Offline statistics and atlas previews do not establish in-game readability or lighting.

Use available game feedback from ordinary and problem scenes, near/far views and relevant poses or part states. Request further visual evidence only when it resolves a material uncertainty. After the user accepts the scoped result, preserve it while adjusting another region.

Hand accepted state and provenance to mod-version-workflow and mod-package. Do not repeat colour correction or re-encode accepted assets just to consolidate a package. Do not claim that an offline plan or combined package was run in game.

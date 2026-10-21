# RE Engine diagnostic layer guide

| Symptom | First evidence to inspect | Likely layer | Common false lead |
| --- | --- | --- | --- |
| ornament leans, floats, or follows the wrong motion | bone hierarchy, weights, bind pose, pivot, physics constraint | skeleton / weight / physics | texture or AVM |
| body hole, stretched vertices, seam deformation | geometry, weights, active components, LOD | mesh / weight / component binding | brightness |
| too metallic, too bright, transparent, glowing | MDF parameters, texture channels, shader, environment | material / texture | mesh geometry |
| washed out, greyed or darkened | user reference, actual shader/slots, local texture input and scene behaviour | material / texture / lighting | treating the symptom word as a unique cause |
| correct near, dark or blurred at distance | mip chain, UV padding, alpha, compression, relevant LOD bindings | texture / material / LOD | global recolouring before inspecting distance changes |
| mip 0 already lacks intended detail | clean original source and texture provenance | texture source / prior processing | recovering lost detail by rebuilding blurred mips |
| correct resource exists but never appears | resolved path, suffix, loader order, cache and reload event | path / loader / cache | resource content |
| instance or component is missing or bound incorrectly | PFB object/component references and paths | PFB / binding | rebuilding textures |
| correct at start, wrong after map or player rebuild | object lifetime, hook state, cached managed objects | runtime Lua | permanent binary corruption |
| AVM toggle has no effect | componentization, body/equipment mapping, preset schema | optional AVM configuration | LuaBone |
| custom skeleton mapping fails at runtime | generated mapping, bone names, target object, reload timing | optional LuaBone branch | AVM preset |
| animation drifts, rotates, floats, or snaps | root motion, coordinate basis, IK anchors, frame rate, transition endpoints | animation / skeleton data | material |

## Evidence hierarchy

Prefer direct evidence in this order:

1. a verified baseline and matched reproduction;
2. file and reference-chain comparison;
3. loader or runtime log evidence;
4. parsed resource data from a verified tool;
5. matched visual comparison;
6. a minimal one-variable experiment.

A visual symptom may narrow the layer but rarely proves the exact field. A log line may show loading without proving that the rendered object used the intended resource. Combine evidence when the decision affects multiple native files.

## Optional systems

### LuaBone

Route here only when the issue involves generated bone configuration, skeleton-to-player mapping, transform application, or runtime replacement behavior. Many appearance changes and character switches require no LuaBone modification.

### Armor Variant Manager

First confirm the asset exposes part-level components compatible with AVM. Distinguish preset authoring and ID mapping from development of the AVM Lua program itself. Changes to AVM's Lua implementation belong primarily to the REFramework Lua development workflow.

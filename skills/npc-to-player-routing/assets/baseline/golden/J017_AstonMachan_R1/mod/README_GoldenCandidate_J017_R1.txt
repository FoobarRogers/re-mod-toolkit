Aston Machan -> Hunter Rig Compare / PL423 / J017 Golden Candidate R1

STATUS
- Original testbuild: user-confirmed working baseline.
- This build: identity-normalized Golden Candidate; static verification PASS.
- In-game verification after renaming: PENDING.

PURPOSE
This package is the Golden reference for the NPC -> Player isolated-model conversion workflow.

NORMALIZED IDENTITY
Historical:
  player/zhst/z017/
  starm024
  stbody024
  sthelm024
  stwst024

Golden Candidate R1:
  player/JRRB/J017/
  JRarm017
  JRbody017
  JRhelm017
  JRwst017

PFB POLICY
- PFB structure is preserved.
- Only known UTF-16LE resource-binding tokens were replaced.
- Replacements are equal-length.
- No blind numeric replacement was used.
- PL423 entry PFB filenames remain PL423 because target equipment slot and JRRB Asset ID are separate concepts.

IMPORTANT GOLDEN BINDING PATTERN
- JRwst017.mesh is the actual full-body Aston Machan mesh.
- JRarm017 / JRbody017 / JRhelm017 mesh+mdf2+chain are identical dummy resources inherited from the working testbuild.
- f_leg423.pfb intentionally points to JRarm017 rather than a JRleg017 resource.
- f_helm423.pfb additionally references JRhelm017.user.
Do not "clean up" this slot-to-resource mapping by inference. Treat it as explicit Golden data.

TEXTURE POLICY
The NPC texture tree remains unchanged:
  natives/STM/dddder4/npc746/
The full-body MDF2 continues to reference:
  dddder4/npc746/body_ALBA.tex
  dddder4/npc746/eyetail_ALBA.tex
  dddder4/npc746/face_ALBA.tex
  dddder4/npc746/hair_ALBA.tex

LUABONE
This package contains four LuaBone custom JSON files renamed to match the private model names:
  JRarm017.json
  JRbody017.json
  JRhelm017.json
  JRwst017.json
Their numeric content is preserved byte-for-byte from the testbuild; all four source JSONs were identical.
For future conversions, generate the values from:
  NPC mesh Local Translation - LuaBone base/f_shadow.json Local Translation

CHANGE SCOPE VS TESTBUILD
Changed:
- private resource directory zhst/z017 -> JRRB/J017
- private resource basenames st*024 -> JR*017
- PFB resource reference strings matching the above
- LuaBone custom JSON filenames
- modinfo / README metadata

Intentionally unchanged:
- PFB hierarchy/components/unknown fields
- mesh/mdf2/chain/user binary content
- LuaBone numeric values
- NPC texture directory and texture files
- target equipment slot PL423
- Golden slot-to-resource mapping

PROMOTION RULE
After an in-game test confirms this renamed build behaves exactly like the original testbuild,
promote status from Golden Candidate R1 to Golden R1 without changing binary resources.

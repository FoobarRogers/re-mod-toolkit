---
name: animation-bake-tuning
description: Tune and bake RE Engine MOT/MOTLIST skeletal animation — bone curves, retiming, loop/transition convergence, foot/hand IK anchors, root motion; locate which slot/clip drives a symptom and compare mod versions slot by slot. 中文触发: 骨骼动画, 动画烘焙, 动作替换, 动作ID, 槽位定位, 过渡收敛. For a repo's own idle/symptom playbook, prefer that repo's skill first; mesh / material / texture / weight / PFB issues belong to reengine-asset-diagnosis.
---

# Skeleton Animation Tuning & Baking

A bake rewrites the keyframe data that every downstream clip and render path depends on, so a wrong parameter rarely fails loudly — it ships as foot sliding, warped legs, or a character that animates in place. The symptoms in this skill are deterministic: each one reappears whenever its parameter is set wrong again. Treat a symptom as a clue about *which* parameter moved, not as a mystery to re-solve from scratch.

Scope: RE Engine `MOT` / `MOTLIST` motion assets and other FK/IK keyframe pipelines with skeletal clips, IK target tracks, root motion, and transition clips. Bone names, script names, and numbers below are examples from one project's bake chain — read them as units and orders of magnitude, not as constants.

## 1. Establish the baseline before touching a value

Record, and keep visible while editing:

- the exact asset under test, its path, and the package version it currently belongs to;
- the timebase field and the source frame count the bake expects;
- which script and which options produced the current asset, and the acceptance command that currently passes;
- which result was last confirmed in game, versus what has only changed on disk.

"Files changed on disk" and "the game reloaded and used them" are different claims. Reinstalling and restarting is part of the loop, and it is done by the user, not by the tooling.

## 2. What a curve means depends on the bone

Before editing a translation, decide which convention that bone uses:

| Translation kind | Typical bones | Meaning | Consequence of editing |
| --- | --- | --- | --- |
| local offset | pelvis, spine, control bones | offset inside the parent's space | changes the visible pose only |
| world target | foot and hand IK bones | where the joint should be in world space | the engine's IK drags the limb; a wrong value reads as sliding or floating |
| root motion | root | the engine consumes it as character displacement | translation inside a transition becomes character movement |

Rotation-only bones still carry the pose, but the same trap applies to twist bones (`*_T` / `*_W` and equivalents): they must follow the same policy as the bone they belong to, or the limb reads as twisted no matter how well the anchors are tuned.

Do not infer the convention from a bone name or from how a value looks. Reverse-engineer it from data:

- untouched vanilla clips inside the same file are ground truth — fit the convention against them and check the residual (a good fit lands at or below ~1e-3 in position and ~1e-2 degrees);
- world position comes from parent accumulation (`pos += q_parent · t`); a bone's own rotation moves the result every frame;
- match bones by name pattern rather than a hardcoded list, so toe, twist, and helper bones fall into the right group.

Two more traps, both paid for (2026-09-20):

- **The skeleton table's bind record is the modeling T-pose, not the render rest.** FK built from the bind table (per-bone translation + quaternion) reproduces a T-pose with horizontal arms while the game shows arms down. The rest translations the engine actually renders live on the model/capture side (one project: the capture JSON's per-bone `base_pos`, which differs from the motlist bind by centimeters). Never mix the two — and a skeleton-table bind that "looks like" a natural pose is a layout misread (the record is translation 3f + pad + quaternion 4f), not evidence against the T-pose.
- **A convention validated on one chain does not transfer to another.** The foot-anchor check (written anchor == FK'd ankle to ~0.001 m) proves the *leg chain* only. Chains with engine-side corrective layers (arms under hand IK, look-at, etc.) do not reproduce world pose from plain parent-accumulated FK — on that project every arm-chain FK reading (elbow spacing, splay angle) was misleading while the leg chain stayed exact. For such chains, operate in **curve-input space**: the engine's mapping from curve values to pose is fixed, so copying or biasing curve values reproduces the source pose without understanding the mapping, and verification is curve comparison plus in-game footage, not offline world-space numbers.

## 3. Invariants every bake must hold

1. **Do not edit the timebase / frame-rate field.** The engine reads the field, not the content, so a field that disagrees with the authored rate takes the asset down at load (a crash on loading a save is the usual shape of this failure). To move content from one rate to another, keep the field and resample the content to the matching frame count.
2. **A static curve cannot blend.** A curve with a single key cannot interpolate, so rewriting it in place can only take the whole curve from one sample — the first frame then holds one bone's value from the source and another from the target. When the key count has to change, rebuild the blob: every curve per-frame, last key equal to the first.
3. **One bone, one strategy.** Mixed static and dynamic curves on the same bone fail the same way as (2), so decide the strategy per bone and apply it to all of its curves.
4. **Change one variable per run,** then prove the unchanged part is unchanged: comparison of untouched clips must come back byte-identical (see `references/verification-hooks.md`).
5. **No speculative byte patching.** Use a verified parser or the project's bake scripts; keep the source artifact, the exact parameters, and hashes so the result is reproducible.
6. **One source per pose chain.** Splicing another clip's curves into a slot only holds if every bone from the root down to the affected chain comes from the *same* source. A waist taken from clip A above legs taken from clip B is a cross-source pose error; the engine's foot IK can absorb it (it re-solves the leg onto the anchored target) **only while the IK target tracks exist** — strip or remove those tracks and the error surfaces at once as warped legs. Prefer copying a whole proven blob over splicing one (section 7).

## 4. IK target tracks

The target is a world position, so it must be computed from the same world the renderer uses — and that is where most foot problems come from:

- **Compute the anchor from the unfrozen parent chain.** If the render side freezes the pelvis to remove root motion, but the anchor is recomputed from the frozen pelvis, the target is pushed off the planted position every frame. The error scales with the frozen amplitude, not with the source, and reads as continuous sliding while standing still.
- **Track the joint the engine actually solves to** (the ankle for a foot), using that joint's world transform. Using the toe bone, or the target bone's own rotation, offsets the target by a constant height and leaves a residual horizontal trajectory — floating feet that twitch.
- **Move the target, not just the rotation.** Interpolate the target's translation onto the *baked* same-name curve. Taking the source's local `base_pos` pins the foot to the character origin; rotating the target while leaving its translation from another source makes the engine's IK drag the foot.
- **Filters must preserve endpoints.** A moving average that simply indexes near the edges shifts the entire curve, so the first frame carries the source pose with a target from somewhere else. Write window functions that hold their endpoints.
- **Verify by independent recompute:** derive the anchor a second way (render-side FK versus the written curve) and compare; they should agree to ~1e-3 with no per-frame drift.
- **A target track is also a pose-correction layer, not just a foot position.** While the target exists, the engine pulls the foot onto the anchored world position every frame and re-solves hip/knee, which silently absorbs errors elsewhere in the chain — including a whole cross-source waist deviation. Remove or strip the target track and that absorption disappears: the residual pose error appears immediately (one project: warped "X"-shaped legs showed up only after the two foot-IK `pos` tracks were stripped, although the same cross-source chain had looked correct for a year with them). Treat "is the target track present?" as part of the baseline (§1), not as an implementation detail.
- **The target that wins may live in another file than the clip you are reading.** The engine's rule is per joint and per frame: **a joint is dragged onto its target whenever *any* contributing layer animates that target's position; when no layer does, the engine does not drag at all and the foot follows the limb chain.** So stripping the target out of *your* clips does not clear the beat — a lower-priority layer can still be supplying one. One project's case: an item-use action library on the base layer carries its own **static** foot target (drinking: 5 keys spanning 2 mm) while the locomotion clips upstairs had theirs stripped; the foot was therefore held on one spot every frame while the leg rotations kept striding, which reads in game as "the legs move but the feet never step, they skate". Two fixes, opposite directions, both measured: clear the *other* file's target tracks (the window then has no target at all → the foot follows the gait, verified by stride length and left/right anti-phase), or restore your clips' targets (also works, but reintroduces the per-frame tug-of-war between a vanilla-anchored target and the mod-skeleton limb chain). Enumerate every layer that can supply the joint before deciding which file owns the fix.
- **Vertical range cannot tell stepping from sliding.** A pinned foot still rises with the leg (one project: an ankle swinging ~0.5 m vertically while its foot was glued down), because what gets pinned is the *contact point*, not the limb. Judge stepping with the **horizontal** travel in root space (stride) plus the **left/right anti-phase correlation** (a real gait sits near −1); a glued foot reads ~0 stride (pinned to the body) or tens of metres (pinned in world space).

## 5. Root motion and the displacement carrier

- **Identify the bone whose translation the engine settles as displacement.** Horizontal translation on it is consumed when entering or leaving a loop through a transition; mid-loop translation is generally not settled. Verify this per asset before relying on it.
- **Freeze explicitly, in a written window.** Zeroing the horizontal translation of the consumed bone over the entry transition is what removes self-rotation on spawn; a window that is not written down drifts the moment the bake is re-run.
- **Choose the carrier by what is parented to it.** Displacement belongs on the bone whose children — wings, hip geometry, attached parts — are supposed to travel with the body. Moving the carrier to another bone changes which attachments follow, and it must be changed in the build script and the acceptance check together.
- **Weight displacement per segment** and ramp the weight in and out, keeping loop closure, instead of switching sources at a single frame.
- **Character speed = the animation's root motion × an engine-side gear factor — it is not the animation's displacement.** Two clips with byte-similar poses *and identical root motion* can run at visibly different speeds (one project: the run and the dash loops differed by 2.7° whole-skeleton average and 0.0 m in displacement, yet the dash measured ~25% faster in game). Conversely, swapping in a clip with different root motion *does* change the real speed (3.90 m/loop → 3.74 m/loop moved the same state by ~4%). So neither "the engine owns the speed, the animation only displays it" nor "the animation's displacement is the speed" is right — the factor multiplies. Measure A→B time per state in game; the offline displacement table cannot rank states.
- **"Pelvis fixed plus feet pinned" bends the legs.** The pelvis deviation has to be absorbed somewhere; keep the pelvis on the source trajectory and re-solve hip and knee to absorb the remainder, then check the correction angle to see whether the choice is sane.

## 6. Transitions and convergence

- **The convergence target is a single pose** — the destination loop's first frame. Converging to "the destination's opening frame sequence" forces the last frame to rewind to the destination's frame 0, which is exactly the pop you see on the final frame.
- **Converge the whole body across the whole window.** Keeping the upper body on the source pose while root motion is already zero produces limbs that stride while the body stands still.
- **Match limb bones by name pattern** so feet and toe bones land in the limb group. A missed bone converges one beat late and shows up as feet snapping together.
- **Close the loop:** after baking, a loop's last frame equals its first frame, verified by a frame step rather than by eye.
- **Judge the last frame by its step from the second-to-last frame**, never against the target's first frame — see the pitfall list in `references/verification-hooks.md`.

### Base-pose bias between loops (the fourth modification class)

Copy / in-place curve rewrite / blob rebuild move *content* between slots. **Bias** changes a loop's resting style in place — e.g. making a run cycle's shoulders match an idle's (one project: 15–19° adduction + internal rotation on both `Arm_00`, joint positions untouched, elbows/twist/spine untouched).

- `q_bias = mean_pose(target) ⊗ mean_pose(source)⁻¹` — quaternion average by dominant eigenvector, sign-aligned to the first sample first — then apply `q' = q_bias ⊗ q` per key. **Left-multiply = a fixed rotation in the parent's space** (physically "adduction against the chest"). Left vs right must be confirmed once in game; the offline evidence cannot decide it (§2: no trusted world-space FK for such chains). The measured mean-vs-mean angle (15–19°) is the sanity reference for the bias magnitude.
- Key count, timestamps, twist bones, elbows, and all other curves stay untouched, so loop closure survives by construction and the motion's own dynamic range (±12–16° in that run cycle) is preserved — the fix reads as "same animation, different resting style".
- Verify offline that after biasing, the cycle mean equals the target mean (0.0°), plus a per-slot semantic diff proving only the declared bones changed; verify in game that the static width/angle shrinks (one project: shoulder-to-head ratio 2.0 → 1.8) while the dynamic envelope survives.

## 7. Locating which clip a symptom belongs to

Before editing anything, establish *which* clip the engine actually plays when the symptom shows.
Offline analysis ranks candidates and reveals techniques; a runtime read decides. The full method
— cross-project facts (runtime ID = the number in the motion name, FSM routing is invisible to
data files, quantized slots read T but not R, container APIs per type), the offline tool shapes
(version diff, slot-vs-slot RMS matrix, speed/pose signature scan, FSM hash forensics), the
runtime probe pattern with its probe-discipline list, and the criteria methodology — is in
[references/baseline-research.md](references/baseline-research.md).

- **Runtime read before deep offline inference.** On the project that produced these tools, the
  offline criteria churned through three candidates across four revisions; one probe log plus the
  operator watching the live panel settled it. The probe is the cheap step.
- **"Resembles" is not "plays".** Which clip looks like the symptom (a pose signature) and which
  clip the engine plays during the symptom (slot routing) are different questions; only the
  second is the answer, and only runtime observation answers it.
- **A relayed attribution is not a constraint.** "Only this reference mod fixed it, so the slot
  must be among the slots it touches" was broken by the runtime read — the guilty clip was
  untouched by every mod in play. Demote such premises to leads and test them separately.
- **When reusing a clip across slots, copy the whole proven blob and repoint the slot.** Curve-level
  cross-source re-coupling re-joins rhythm-critical pairs by hand — an IK target whose stride
  rhythm differs from the root translation it rides with reads as per-step dragging.
- **Read the node weights, not the node at index 0.** A layer can hold several motion nodes blended by weight, and the "motion ID" you get at index 0 is the **first name in that group's list**, not the clip that dominates the pose. On one project the dash group (`plc_*_012_013_038`) reported `012` at weight **0.00** while `038` sat at **0.96** — every "the dash plays clip 012" conclusion drawn from the index-0 read was wrong, and it cost a long detour. Read the node count and every node's ID *and* weight (`getMotionNodeCount`, `getMotionNode(i)`, per-node `get_Weight`; some builds also expose a highest-weight getter), and treat the weight as the answer. The group of names in the data file is exactly the engine's blend set: the list order — not the runtime weight — decides what index 0 reports.
- **A whole-skeleton average hides chain-local differences, so it cannot decide "these two clips are the same".** Two clips differing by 2.7° on average across all bones were described as "identical", while the torso chain actually differed by **13°** and the limbs by 16–22° — and that chain-local difference was the entire visible difference (one read as upright, the other as leaning). Diff **per bone, grouped by chain**, and look at the chain the symptom lives on before treating two clips as interchangeable; and when a conclusion was drawn from a whole-skeleton metric, revisit it.
- **Ready-made implementations** of the offline tools live in this skill's `scripts/`: a parsing
  library (`motlist_lib.py` — slot-header offset table, skeleton/track/hashes, float-vs-quantized
  gating, quaternion helpers) and thin CLIs (`scan_speeds.py`, `scan_pose.py --rank`,
  `slot_matrix.py`, `cmp_slots.py`, `diff_motlists.py`, `copy_slot_blob.py`). Run them against
  the real asset before trusting a rewrite; their docstrings carry the paid-for traps.

## 8. Should this clip be rebuilt at all

Rebuilding a clip that is not a transition destroys gameplay motion. Judge with direct measurements; "this clip carries displacement" and "its last pose looks like the idle" are indirect features that have both misclassified real gameplay clips, because recovery and dodge clips end in the idle pose by design.

| Direct criterion | Transition | Gameplay action |
| --- | --- | --- |
| body turn angle | tens of degrees | large continuous turn (one project's dodge roll: ~185°) |
| first frame against the predecessor loop | connects within a few degrees | 25–32° off, cannot connect |
| hip height (local pelvis Y) | inside the posture range | kneeling or prone: a fraction of standing height |

Set a turn-angle threshold that rejects the gameplay clips, keep those clips byte-identical to the source, and assert their root motion is preserved.

## 9. Symptom index

Summary below; the full table with data signatures, measurement method, and root causes is in [references/symptom-index.md](references/symptom-index.md). Read it when a symptom needs diagnosis rather than when tuning parameters.

| Symptom in game | Data signature | Root cause |
| --- | --- | --- |
| continuous foot sliding while standing | anchor oscillation several times the source's | anchor recomputed from the frozen parent chain |
| feet floating, flickering | target offset by a constant height each frame | anchor taken from the end bone or the target's own rotation |
| feet pinned to the origin | anchor values at local magnitude | translation taken from the source's local base position |
| gliding / treadmill | position static, legs striding | limbs or IK targets not converged over the whole window, or rotation changed without translation |
| self-rotation of 75–90° on spawn | horizontal translation on the root-consumed bone | source locomotion trajectory settled as root motion |
| legs bent or warped, hips off by ~0.2 m | "pelvis fixed, feet pinned" | displacement not weighted per segment, no hip/knee re-solve |
| one-frame jitter at clip start | T curve with many keys, R curve with one | static curve can only take the whole curve from one sample |
| body turn of ~185° on a game action | root displacement zeroed on a gameplay clip | clip misclassified as a transition (section 8) |
| last frame pops | per-frame step at the end far above the envelope | convergence target was a frame sequence, not one pose |
| a large step-out when the character stops | final-frame ankle offset tens of cm | the source transition ends in a different stance than the destination loop |
| twisted limbs | difference confined to `*_T` / `*_W` bones | twist bones left on a different policy |
| head tilt only when another character is nearby | large local head/neck deviation plus engine look-at | unresolved class of issue; damping head curves is a trade-off, not a fix |
| shoulder width looks different between two anims, elbow spacing unchanged | per-joint world positions nearly identical; the difference sits in joint rotation (adduction/internal rotation) | pose-driven silhouette, not skeleton geometry — fix with a base-pose bias on the joint curves, not by moving anything |
| warped / "X"-shaped legs after splicing one clip into another | cross-source waist vs limbs; the IK target `pos` tracks are absent | the cross-source pose error lost the IK-target absorption layer (section 3.6) |
| lower body stops stepping during an interaction (drinking, picking up) while the leg rotations keep striding | the foot-IK target's world coordinate is nearly constant inside the window, while the ankle's vertical range is normal | only one layer still supplies a target and it is **static** — the clip under inspection has none (section 4) |
| sibling clips of one loop family read "upright" vs "leaning" | torso chain differs ~13°, whole-skeleton average only ~2.7° | chain-local difference hidden by a whole-skeleton metric (section 7) |

## 10. Verification

Design the acceptance check before tuning, and run it on the baseline first so you know what "passing" looks like. Hook patterns, the minimum set, and their traps are in [references/verification-hooks.md](references/verification-hooks.md). Minimum:

- independent recompute of every derived value (a second algorithm, not the same code path);
- written curve versus render-side FK, expecting near-zero difference;
- geometric range checks (joint height while planted, loop closure);
- byte-identical comparison for clips that must not change;
- frame-to-frame step envelope, with the last frame called out separately;
- acceptance flags identical to the build flags — a mismatched carrier or mode flag reports failures for a healthy asset;
- **in-place rewrites must be declared to the verifier.** An in-place edit (same key count, values only) does not move slot start offsets, so a verifier that detects rewritten slots by offset deltas sees nothing — the edited slots pass the "everything else byte-identical" gate silently. Declare them (`--extra-rewritten`-style), let the declared-set check degrade to "changes ⊆ declared" for that run, and prove the change scope with an independent per-slot semantic diff (curve-level, NaN-normalized — not byte comparison of neighbouring slots).

## 11. Workflow

1. Run the acceptance command on the current asset and record the result.
2. Change one thing; keep every other clip untouched and prove it.
3. Re-run acceptance; a previously passing check that now fails is information, not noise.
4. Compare fidelity where the change is structural (side-view overlap and difference metrics for legs and feet).
5. Package the asset with the project's packaging skill.
6. Hand off for in-game verification; reinstall and restart are required for anything to take effect.

## 12. Do not promote case evidence to rules

The numbers and behaviours quoted here were measured against one project's asset chain. In particular, how a given engine build interprets the frame-rate field, when root motion is settled, what the IK anchor convention is, and how much convergence error is acceptable must be re-measured for a different asset, character, engine build, or capture source. Carry the method over; re-derive the values. When a conclusion is later contradicted, record the counter-evidence next to the rule rather than quietly narrowing the rule.

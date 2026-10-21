# Symptom Index

Expanded form of section 9 in `SKILL.md`: for each symptom, the in-game appearance, the measurement that proves it, the root cause, the fix, and the acceptance hook that keeps it fixed. Read this when diagnosing; the parameter tables in the parent skill are for tuning.

Numbers are labelled with the project they came from and are examples of magnitude, not thresholds to copy.

---

## 1. Continuous foot sliding while standing

**Appearance:** the character stands still, the feet drift or skate.

**Measurement:** do not try to read this off a recording — camera distance, rain, and NPCs make the video unusable for quantification. Compare the *written* anchor curve against the capture source instead, using two independent algorithms:

```
original = written_anchor + (original_parent_world - frozen_parent_world)
```

Then measure the horizontal oscillation range per animation segment. In one project the written anchor oscillated 5.59 / 5.40 cm while the real foot moved 1.37 / 1.21 cm.

**Root cause:** the anchor was recomputed from the *frozen* pelvis. The anchor is a world target, so freezing the render side and recomputing from the frozen pelvis pushes the planted foot away, and the engine's foot IK follows the target faithfully. The error scales with the freeze amplitude — which is why a 1.4 cm real movement became a 5.6 cm target oscillation.

**Fix:** compute anchors from the original, unfrozen parent chain, every frame. The first frame is unchanged (the freeze baseline is the first frame), and the standing-segment range returns to source level.

**Rule of three:** freezing the pelvis to remove root motion (correct) + leaving the anchor at its original world position (correct) + computing it from the *original* pelvis (correct) — dropping any one of the three reintroduces the bug.

**Hooks:** independent recompute of the anchor from the rotation matrices; written anchor versus render-side FK ankle position (zero expected deviation); ankle height while planted compared against the vanilla range; "planted while standing" assertion.

---

## 2. Feet floating, flickering, or twitching

**Root cause:** the IK anchor was taken from the toe bone instead of the ankle, and its translation used the target bone's own rotation instead of parent accumulation.

**Measurement:** the target sits a constant distance below the joint (about 0.07 in one project) and leaves a residual horizontal trajectory (0.194 m) that the eye reads as flicker.

**Fix:** anchor = the joint's world transform (ankle for the foot), translation from parent accumulation. Recover the exact convention by fitting against vanilla clips that were never rewritten — one project's fit residual was ≤0.0014 in position and ≤0.001° in rotation, which is what a correct convention looks like.

**Note:** hand IK targets are often *not* affected by the same mistake, because their parent is a spine bone rather than the root; a static target under a spine bone is legitimate and does not drag the arm.

---

## 3. Feet pinned to the character origin

**Root cause:** the IK target's translation was taken from the source's local `base_pos` — a local-space value used as if it were a world target. The engine then pins the foot to the origin.

**Related failure, same family:** changing only the target's rotation and leaving translation alone. The rotation converges while the target does not, so the engine's IK drags the foot — the classic gliding look.

**Filter trap:** a moving average with generic edge handling *shifts* the whole curve rather than removing spikes. In one project a 9-frame window moved first-frame hand and foot targets by 1.4–35 cm, i.e. the pose came from the source while the target did not. Use endpoint-holding windows; verify the first frame explicitly after any smoothing.

**Second place the family appears:** a hold parameter that keeps the upper body on the source pose (to let a stop animation finish naturally) must not be combined with a zeroed hold on the legs. Root motion is already zero, so legs that still stride produce "legs moving, body stationary". Leg determination must be name-based — a missed toe bone lands in the upper-body group, converges a beat late, and shows as feet snapping together.

---

## 4. Self-rotation on spawn, and per-segment displacement weighting

**Root cause:** the capture contains an NPC's horizontal walk trajectory on a pelvis/root chain bone (in one project up to 0.19 m offset, 1.33 m per lap). The engine settles that as root motion when entering the idle through a transition, producing 75–90° of self-rotation.

**Fix that worked:**
- zero horizontal translation of the consumed bone inside a written transition window;
- carry the source displacement on the bone whose attached parts must travel with the body, from the segment where the pelvis should return to the source position;
- ramp the weight in and out across the boundary segments and keep the loop closed;
- re-solve hip and knee to absorb the remainder (in one project the residual needed only about 2.9°), recomputing the ankle so the foot keeps its orientation.

**Magnitude to sanity-check against:** "pelvis fixed plus feet pinned" bent the legs badly — the hip position differed by up to 0.19 m. That difference *is* the "body warped" report.

**Hooks:** no horizontal translation inside the transition window; displacement in the transition equals the source pelvis; carrier matches the declared mode; pelvis Y oscillation preserved; dense key coverage on the carrier's translation.

**Carrier change history:** when the carrier bone changed between versions, everything that hangs off the new carrier had to follow the body during that segment. The consequence is that the build script and the acceptance flags must be changed *together*; running acceptance with the previous carrier reports two failures on a healthy asset.

---

## 5. One-frame jitter at clip start

**Data signature:** on one bone, the translation curve has many keys (75 in one project) while the rotation curve has a single key.

**Root cause:** in-place rewriting can only take a static curve's single sample for the whole curve, so the first frame pairs the source's pelvis position with the target's pelvis orientation for one frame before recovering.

**Deeper cause worth checking:** the vanilla transition clip may not have removed the angle the new asset removes, so the "static jump" is in fact a large twist applied inside one frame.

**Fix:** rebuild each motion blob whose key count changes — all curves per-frame, last key equal to the first. In-place editing cannot express this.

---

## 6. A pop on the last frame

**Root cause:** the convergence target was written as a function of the output frame number, so it sampled the destination animation's frames instead of one pose. The last frame then had to rewind from the destination's frame `nf` back to frame 0 — and that gap *is* the pop. In one project it measured 24–31° on the arms; the legs moved only 4–17°, which is why the arms exposed it first.

**Fix:** the convergence target must be a single pose: the destination's first frame.

**Criterion trap:** "last frame versus target's first frame" always passes, because the last frame is forced to equal it. Measure the per-frame step between the last frame and the second-to-last frame instead; one project's acceptance allows ≤0.35° there, where the broken version showed 24–32°.

**General technique:** after removing an isolated end-of-clip snap, re-measure the mid-clip per-frame envelope (it should move by no more than a small fraction of a degree per frame) to prove the problem was not merely relocated.

---

## 7. Gameplay clips misclassified as transitions

**Root cause:** a dodge/roll clip in the rearmed stance — 74 frames, ~185° of continuous body rotation, 4.60 m of root travel — was treated as a move-to-idle transition and had its root displacement zeroed. In game, the dodge roll happened in place and the player could not evade.

**Why it was misclassified:** "the last pose looks like the idle" is not a sufficient criterion — recovery and roll clips *end* in the idle pose by design.

**Distinguishing criterion:** body turn angle. The current tooling prints the turn peak per clip and refuses to rebuild anything above the threshold.

**Vanilla-restored clips carry their own signatures:**

| Kind of clip | Signature |
| --- | --- |
| dodge / roll | ~185° body turn, several metres of root travel, tens of frames |
| knockdown recovery / get-up | first-frame hip height a fraction of standing (kneeling/prone), torso flexed forward, long forward travel |
| dodge-derived crouch | hip height drops through a mid value and returns while standing up |
| crouch walk | hip height cycles between standing and half-crouch values |

**Hooks:** byte-identical to vanilla; root motion preserved.

**Comparison pitfall:** do not slice a clip using "the next clip's start offset" — appended writes change neighbour boundaries and invent differences. Normalize NaN in curve values too, or `NaN != NaN` reports a false difference.

---

## 8. A large step-out when the character stops

**Root cause:** the vanilla stop transition ends in the *vanilla* stance (one foot forward, the other loaded), while the replacement idle has a squared stance. The difference in the final frame has to be absorbed by a stride, which the player sees as an exaggerated step-out.

**Fix:** converge frame by frame and spread the difference across the whole transition — keep the stride peak, pull it back over the second half, and end on the destination idle's first frame. One project measured the ankle difference going from +17.2 cm to 0.0 cm while the stride peak only fell from 0.43 m to 0.40 m.

**Criterion detail:** the tightest test was the first frame against the predecessor loop — a couple of degrees for the correct predecessor, roughly double that for the next candidate.

---

## 9. Head tilt that only appears near other characters (unresolved class)

**Appearance:** the head tilts during a deep "look down at the legs" phase of the idle when an NPC or pet is nearby, but not when alone. The only difference is the engine's look-at being active.

**Measurement:** the engine's own idles keep head pitch in single digits and neck/head local rotation near identity. The replacement idle's local deviation reached ~32° at the neck and ~56° at the head, with ~29° of world roll amplitude — so adding yaw on an already-pitched head produces roll.

**Interim attempt:** inserting head and neck rotation curves back toward the standing pose (keys unchanged, values rewritten in place), leaving body, legs, anchors, and control bones untouched. It reduced the local head deviation from 56.5° to 19.8° and the world roll from 29° to 7°, and passed all acceptance checks, but cost roughly two thirds of the idle's head motion and did **not** fully cancel the tilt. Not shipped.

**Lesson:** a passing acceptance suite is not evidence that an appearance problem is solved, and damping amplitude is a trade-off to be decided with the user, not a fix to apply silently.

---

## 10. Telling "vanilla content" from "added by the mod"

- Compare the mod's asset against the vanilla asset for the same slot map: one project's difference was only the writing method (per-frame, float32, u16 timestamps, extra twist bones), with translation trajectories identical to ≤0.0002 mm. Whether rotation was also rewritten stayed undecided, because vanilla rotation uses a quantized codec.
- The authoritative reference is the vanilla file with the same slot map and IDs.
- **Parser trap:** the convenience reader that assumes u16 timestamps and 12-byte float3 vectors misaligns on a file that uses u8 timestamps plus a quantized region, inventing large rotations that are not in the data. Validate a parser against a known-good clip before trusting its output.
- Horizontal translation on pelvis and waist bones is often already zero in transition clips, because the source's travel lives on the root and the root translation is zeroed wholesale. Zeroing the pelvis again only twists it on the first frame.

## 11. "The shoulders look different between two animations" with unchanged joint positions

**Appearance:** the run cycle reads as broad-shouldered, the idle as narrow (or the reverse); the user perceives the shoulders "shrinking inward" when the character stops.

**Measurement:** do not start from the screenshots — different camera angles fake width differences. FK the joint positions first: in one project the elbow-to-elbow spacing was 36.9 cm (idle) vs 36.8 cm (run) — the skeleton geometry was identical. The real difference sat in the *joint rotations*: `Arm_00` adduction + internal rotation of 15.7°/18.6° between the two cycles' mean poses, with spine differences only 3–8°. Decompose per bone before assuming "shoulder width" means anything geometric.

**Root cause:** pose-driven silhouette. The joint position (bind translation) never changes — the *rotation* of the upper-arm root turns the deltoid and upper arm inward, which reads as a narrower shoulder in the silhouette. The fix class is a **base-pose bias** on the joint's rotation curves (SKILL.md §6), not touching any translation.

**Fix:** `q_bias = mean_pose(target) ⊗ mean_pose(source)⁻¹` applied per key, left-multiplied (parent-space). Key count, timestamps, twist bones, elbows untouched. Two traps: (1) left vs right multiplication is decided by one in-game check — offline FK cannot decide it for chains with engine corrective layers; (2) never copy the *target's* spine/waist curves along with the shoulder intent when those curves carry an orientation-compensation layer (one project's idle waist carried a −30.7° heading correction from the capture bake — copying it would rotate the character).

**Hooks:** after biasing, the cycle's mean quaternion must equal the target's mean (0.0°); per-slot semantic diff proves only the declared bones changed; in game, static width ratio shrinks (measured 2.0 → 1.8 shoulder-to-head) while the dynamic swing envelope survives, and no width pop appears at gait transitions.

**Cross-check discipline:** vision-model reports on screenshots are leads, not verdicts — one project's "wide shoulders at spawn" was a cape misread by the model and contradicted by the user watching the actual clip. Combine model reports with pixel-extracted frames against a same-pose baseline, and let the user's own eyes settle conflicts.

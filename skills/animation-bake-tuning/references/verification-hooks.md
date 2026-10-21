# Verification Hooks for Animation Bakes

Acceptance checks are what turn a set of invariants into something that cannot silently regress. Design them before tuning, run them on the baseline first, and treat a newly failing check as information rather than noise.

## Design patterns

**Independent recompute.** Derive each value a second way and compare, rather than re-reading the value the bake just wrote. A foot anchor, for example, can be computed from the rotation matrices directly and then compared against the written curve; agreement at ~1e-3 is what "the convention is right" looks like. A check that shares the bake's own code path proves nothing.

**Written curve versus render-side position.** Compare the curve that was written against the joint position produced by the forward kinematics the renderer uses. The difference should be zero for IK targets, since the engine solves to exactly that target.

**Geometric range checks against vanilla.** Range-check derived quantities (joint height while planted, pelvis height per posture, stride amplitude) against values extracted from untouched vanilla clips, not against the current candidate. This is how you avoid encoding an existing bug as the expected value.

**Byte or hash identity for clips that must not change.** Every bake that rewrites part of a file must prove the rest is untouched. Keep a hash per clip, not one hash for the file.

**Per-frame step envelope.** Compute the step between consecutive frames across the whole clip and assert the envelope. This catches pops anywhere, including ones a first/last-frame check would miss, and after a fix it proves the problem was not merely moved elsewhere.

**Loop closure.** For loop clips, the last frame equals the first frame after baking; verify numerically rather than visually.

**Mode and flag consistency.** Whether the acceptance run describes the same asset the build produced is itself a check: a carrier/mode flag that differs from the build's makes a healthy asset report failures.

## Minimum set for a motion bake

| Check | Proves |
| --- | --- |
| independent recompute of anchors and derived curves | conventions are implemented, not assumed |
| written versus rendered joint positions | IK targets and the render side agree |
| joint height and posture ranges versus vanilla | no floating, no planted-foot drift |
| byte-identical comparison of untouched clips | nothing else regressed |
| per-frame step envelope, last frame called out separately | no snap at either end |
| loop closure for loop clips | the clip can be entered and re-entered |
| mode flags identical to the build | the acceptance run describes the candidate |
| displacement in the transition equals the source, none outside it | no root motion settled at the wrong time |

## Traps

- **A check that always passes.** "Last frame versus the target's first frame" cannot fail once the last frame is forced to equal it. Measure the last frame against the *second-to-last* frame.
- **NaN comparisons.** Curve data can contain NaN; normalize it before comparing, or `NaN != NaN` reports a false difference.
- **Neighbour-based slicing.** Do not cut a clip out of the file using "the next clip's start offset". Appended writes change neighbour boundaries and invent diffs. Compare by slot map and IDs.
- **Stale defaults.** Acceptance scripts tend to keep a default path pointing at an older version. Pass the asset and the mode explicitly, and confirm the file the check actually opened.
- **Wrong reference.** Some checks compare against the previous bake, others against vanilla. Decide which one each hook needs; a vanilla comparison will flag intentional animation changes.
- **All green is not "looks right".** Passing checks only prove the properties that were written down. A visual problem outside those properties (see symptom 9 in `symptom-index.md`) can pass every hook.
- **Thresholds copied from another project.** Recalibrate from the vanilla distribution of the asset in hand; a threshold that is too tight turns normal variation into failures, and one that is too loose stops catching the regression it was written for.

## Recording results

For each acceptance run, record: the asset path, the mode flags, the hook list with thresholds, and the measured value for each hook. Baseline results are the interpretation key for every later run — without them, a failure cannot be distinguished from a check that was always failing.

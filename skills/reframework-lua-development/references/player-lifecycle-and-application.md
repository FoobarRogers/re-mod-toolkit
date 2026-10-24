# Player lifecycle and application

Apply these rules to player-scanning REFramework Lua. Treat MHR examples as evidence for the tested project, not universal RE Engine APIs or timing guarantees.

## 1. Map the actual actors before optimizing

Identify the authoritative source, identity key, lifetime, readiness signal, and write phase for each supported context: local gameplay, equipment preview, tent, event/CG actors, remote players, and title/load transitions. Do not assume that all contexts use MasterPlayer or that a preview is the gameplay actor. Trace object identities when that relationship matters.

Treat gameplay actor → preview actor → rebuilt gameplay actor as a possible observed lifecycle, not a mandatory sequence. A non-null managed object can remain callable after it stops being the current player. Do not let UI persistence of an old actor authorize runtime writes. Distinguish API failure/absence from confirmed unequipped state; retain user intent while deferring unsafe writes. Preserve or explicitly revalidate existing scene fallbacks before narrowing discovery to MasterPlayer.

## 2. Separate caches and their invalidation

| State | Cache key / ownership | Invalidate when |
| --- | --- | --- |
| Loaded configuration and current selections | Existing project configuration identity | Explicit edits, reload/reset contract, relevant file refresh |
| Final appearance or transformation intent | Configuration identity plus selection/rule revision | Manual choice or rule result changes |
| Current actor binding | Actor role plus verified instance generation | Authoritative identity change, observed absence/reacquisition, context/reset |
| Parts, Mesh, skeleton and joint handles | Actor instance plus resource generation | Parent replacement, invalid handle, resource replacement or relevant structural change |
| Application status | Actor/resource generation plus intent revision and target | New instance/resource, new intent, incomplete or failed application |

Preserve the project's established selection-sharing semantics; do not invent independent per-player JSONs. Keep application records per instance even when configuration is shared across players. On a local rebuild, evict only related instances and descendants unless a verified whole-scene transition requires broader invalidation. Clear stale references without reloading unchanged JSON on every rebuild.

Do not treat an address alone as eternal identity. Use available lifecycle/generation evidence; reacquisition after an observed gap must not inherit an old completion record. Check resource identity as well as GameObject identity: Mesh or skeleton can change while its parent address stays unchanged. Material/joint counts alone cannot prove that names, order, or mapping stayed the same. Rebuild name/index mappings on the relevant resource changes.

## 3. Keep detection, discovery, and writing separate

Use a verified transition hook when one exists. Otherwise use a cheap bounded identity check at the required responsiveness, cached discovery in stable periods, and bounded retries during reconstruction. Avoid repeated full scene walks, disk reads, reflection, or serialization in hot paths.

Check the dependency feeding the observer: a per-frame observer reading a stale directory entry is still stale. Compare the authoritative actor with the cached actor before tuning downstream intervals. Do not assume that shortening a parts-cache TTL fixes actor-directory lag.

Select cadence separately for current identity checks, part/resource discovery, transformation inputs, and writes. Keep gameplay-critical inputs such as form switches or skill windows responsive. A mod that is inactive on the current equipment may sleep its expensive work, but must retain a reliable wake-up path for new actors or newly matching parts. Never infer “not equipped” from “target not loaded yet.”

Trigger bounded fast discovery on meaningful identity/resource changes. Do not renew the fast window forever on irrelevant child churn or a permanently missing optional part. After the bounded window, continue a slower recovery path for late arrivals; avoid both endless fast scanning and permanent abandonment. Choose parameters from measurements; frame counts and seconds are not interchangeable at varying FPS.

## 4. Apply the newest intent to the newest ready instance

Treat both conditions as application triggers: same instance with changed intent; changed instance/resource with unchanged intent. Preserve the direct manual-UI apply path. Reuse the current choice on reconstruction; do not silently replace it with defaults or write old Body-ID intent onto newly selected equipment.

Within a reconstruction pass, acquire the current actor, resolve its current equipment/resource identity, obtain the matching latest intent, and apply to ready targets without adding an unnecessary normal-update delay. If identification or target readiness is unknown, mark pending and retry. Do not require all five armor slots when the script supports individual pieces; define readiness from the actual target contract.

For new or revised application bookkeeping, distinguish attempted work from completed work. Mark success only for targets successfully processed under that contract; keep required but unavailable targets pending. Optional or non-applicable targets must not keep a character pending forever. Do not introduce a broad bookkeeping rewrite into a proven minimal identity fix without evidence that it is needed.

Use read-before-write or differential writes when meaningful for the property. Treat successful setter calls as API-level evidence, not proof that the player saw the final pixels. Do not temporarily hide the entire actor to conceal flashes unless that behavior is explicitly part of the agreed design.

## 5. Adapt the write policy to the feature

| Feature | Reusable mechanism | Additional evidence required |
| --- | --- | --- |
| AVM material/mesh visibility | Preserve intent; bind and apply on actor/resource changes | Distinguish whole-Mesh enable from per-material enable; material names/index mappings; competing visibility writers |
| Transformation script | Cache discovery; respond to form/rule changes and rebuilds | Required input cadence, per-player equipment gating, HUD/event callback duplication |
| LuaBone or custom bone controller | Reacquire actor/skeleton/joints; cache mappings per generation | Animation/IK/physics overwrite timing, coordinate space, absolute versus additive writes, restoration ownership |

Do not extrapolate AVM's stable-version skip to bones. Animation, IK, or physics may overwrite bone values every update even when the actor and configuration are unchanged. Measure relevant phases and identify the writer before lowering bone write frequency or moving callbacks. Cache expensive discovery independently of required recurring writes.

For additive bone changes, derive each result from a known uncontaminated baseline; do not accumulate a delta onto a previously modified result. Recapture baselines only under a defined new-resource/reset contract. Restore only the matching valid instance and properties owned by this script, respecting other writers. Keep existing LuaBone compatibility switches and tested compensation semantics unless the task requires changing them.

## 6. Collect discriminating evidence

Before a fix, choose the smallest observation that distinguishes the leading explanations. Record as available: context, frame/phase, monotonic timestamp, authoritative actor ID, cached actor ID, observed resource ID, detected equipment ID, intent revision, readiness, apply attempt/result, and actual sampled property. Use one time basis for durations; do not mix CPU time, wall time, frame counters, or unrelated clocks.

Keep diagnostics default-off/manual, bounded in duration and event count, and save outside the per-frame path. Separate scan counts, API calls, writes, and measured CPU cost. A call count is not time; a disabled write loop is not necessarily a cheap discovery loop. Measure release performance with intrusive probes disabled.

State the probe's coverage. A MasterPlayer/event probe does not automatically cover preview actors, another outfit's material names, or unknown native writers. Sampling before/after render preparation does not prove first-visible-frame behavior or establish which script wrote a property. Record phase order rather than assuming callback ordering. No observed transient means no transient within the sampled coverage.

## 7. Verify and keep scope bounded

Compare before/after with the same scenario, target set, and probe. Exercise relevant transitions: cold entry without the outfit, switching back from another mod, confirmed equipment exit, tent, manual group/combo changes, CG entry/exit, reset/title reload, and remote players. Select tests that address the changed path; do not claim unrun cases passed. Preserve a known successful CG path as a control rather than rewriting it to match normal gameplay.

Use offline tests for still-callable old actors, identity changes, observed gaps/address reuse, same-parent resource replacement, partial assembly, manual intent updates, bounded recovery, and remote cache isolation where relevant. Parser and mocks do not establish real-game timing. Preserve accepted test artifacts and record limited acceptance separately from release promotion; use mod-version-workflow and mod-package for those transitions.

## 8. Evidence anchors and limits (MHR, 2026-10-24)

- BladeSwitch ScanCache: cold non-BS → BS, Evil → BS, and tent observations showed no overlap. Menu protection was not responsible for that result. Earlier open/close hooks ran as repeated process checks and caused almost continuous scanning; names were not reliable transition semantics. Fixed-length menu coverage is not a universal requirement.
- AVM ScanCache test1, report `EvilVisibilityTrace_test1_1792830788_1.json`: four Evil instances initially exposed all 45 tracked materials; 13 switched off together after about 155–478 ms, with stable sampled object/Mesh IDs. This was evidence of delayed application, not proof of a competing writer.
- Existing Rebuild CG path, report `EvilVisibilityTrace_test1_1792831784_2.json`: two event actors reached the intended 32-on/13-off state one sampled frame after target appearance; a later rebuilt ordinary player took about 236 ms. Preserve this successful path; do not claim CG needed the new ordinary-player observer.
- AVM ScanCache test1fix1, report `EvilVisibilityTrace_test1_1792834636_1.json`: two newly observed Evil instances were already 32-on/13-off at first sampling in both phases, with no sampled rebound. The patch added authoritative local identity acquisition before the existing observer. Accepted baseline: `3.1.3 Rebuild fix1`; preview switching still briefly flashed visually and was retained as a known limitation.
- Treat these results as support for timely instance rebinding, not a universal zero-frame guarantee, proof that every delay equals a 0.5-second TTL, or evidence that 0.5 seconds always suffices for loading. Do not infer cat-outfit timing from an Evil-only target list.

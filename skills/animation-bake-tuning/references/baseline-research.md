# Baseline research: locating the clip behind a symptom

Methods and tool shapes distilled from one project's multi-week investigation of "a specific
locomotion state plays a stiff-armed run" — four rounds of candidate churn offline, then one
runtime log closed it. The lesson that shapes everything below: **build the runtime read first,
then reason offline** — the reverse order turned a one-probe answer into weeks of analysis.

The tool paths quoted are from that project's repo (`tools/`); treat them as shapes to copy or
scripts to reuse directly if you have the repo. The criteria and the traps are the transferable
part. Re-derive all numeric constants for a different asset.

## 1. Cross-project facts worth checking before relying on them

- **Runtime motion ID = the number in the motion name** (`011_Lo` ↔ id 11). The motlist file's
  slot index is a different numbering (`011_Lo` sat in file slot 7; `122_Loop` in file slot 82).
  Both orderings exist; align them by name, never by position.
- **The FSM does not bind states to motions in any data file.** `motfsm2` contains state-name
  hashes (murmur3_utf16) only. State names like `escape_to_run` prove a state exists, not what it
  plays — the routing is only observable at runtime.
- **Slot-name strings are not parsed at runtime** (one project shipped 20 corrupted slot names,
  game played fine). Consequences: names are safe to sacrifice in a rebuild, and name-based
  offline reverse-engineering of routing is a dead end by design.
- **Quantized-layout slots:** the R curve uses quantized codecs (fmt family `0x2x1112`) and is
  unreadable without solving the codec; the T curve is plain float3 and readable. So a full-slot
  speed scan works on every slot, while rotation comparison only works on float-layout slots.
- **Container APIs differ by type.** `via.motion` wrapped containers iterate with
  `get_Count()` + `get_Item(i)` (0-based); `System.Array` iterates with `get_elements()`.
  Lua's `#` on a managed container raises (`attempt to get length of a sol.REManagedObject*`).
  Using one type's method on the other is a silent dead end.
- **Banks and layers.** A character carries many motion banks simultaneously (idle / field /
  damage / tool / weapon in one project: bank 0, 1, 2, 100). Log `bank:id` together. Layers:
  layer 1 is the whole-body driver; upper layers carry overrides and read as `node=nil` /
  `EmptyMotID` (4294967295) when idle — an upper-body symptom may live in either place, so log
  every layer.

## 2. Offline tool shapes, by research phase

### Phase A — what did each mod version change?
Per-slot semantic diff between two motlists: cluster by a per-curve digest, not by bytes.
Traps paid for: identical slot counts with different content mapping produced 139 phantom
"differences" once; compare only curves that have bone names (non-bone hash tracks pollute the
diff); normalize NaN. Output: the exact slot set each version touched, and a four-way
classification (untouched / one-side / both-sides-differently).

### Phase B — slot-vs-slot matrix: what technique did the author use?
RMS matrix over rotation curves inside one motlist. RMS ≈ 0 between two slots = the same data
was written into both (a copy technique); a slot similar to nothing = an independent rewrite.
This answered in one run what three rounds of inference could not: whether a reference mod had
copied a normal-run clip into the suspect slot (it had not — its rewrite was an independent clip).
Pair it with a per-bone diff between two slots (same-length clips): which bones carry the
difference tells you the nature of the change (legs vs upper body vs `*_T`/`*_W` twist bones).

### Phase C — speed and pose signatures
- Full-slot speed scan from the T curves (works on quantized slots too). Speed bands
  (idle / walk / run / sprint) collapse a candidate list fast — in one case from 14 slots to 1.
- Pose scan of loop slots: torso pitch mean and full-cycle range (a phase-independent criterion —
  a clip whose torso leans back at every phase can never look "leaning forward"), hip height
  (local pelvis Y: standing / running / crouched bands), hip sway, stride, knee bend.
- Stride from the engine's own `Foot_IK` anchor displacement, not from a thigh-bone angle —
  a thigh atan2 sweeps across ±180° during a leg lift and invents a fake swing amplitude.
- A `--rank` mode that sorts by an explicit symptom signature ("stiff upright run" = most
  upright torso + highest hip + smallest sway; rank each criterion, sum the ranks, no fitting)
  keeps the judgment reproducible. Write the signature down before ranking.
- **Known limit:** a pose signature says "this clip resembles the symptom", never "the engine
  plays this clip during the symptom". Confusing the two cost four rounds of candidate churn.

### Phase D — FSM forensics
Hash state names out of `motfsm2` (murmur3_utf16; a 48/82 hit rate is normal). Useful to prove
which states exist (`escape_to_run`, `escape_to_dash`) and to bound the question; useless for
routing (see §1).

## 3. Quantized-layout slots: what an investigation can and cannot use

Quantized slots carry vanilla content and cannot be pose-compared, but the investigation still
has working channels — ordered by cost. Gate every slot float-vs-quantized first (`ML.header_ok`):
the split itself is evidence, since float = rewritten by a mod, quantized = untouched by everyone.

**Still available offline** (plain-float3 T curves + header fields):
- speed / net displacement / frame count → band candidates by locomotion gear (`scan_speeds.py`
  works on every layout; one quantized suspect was pinned to the sprint gear this way);
- whether a slot changed between two files (`diff_motlists.py` is layout-independent: the same
  quantized bytes hard-read to identical values, so "semantically equal" is trustworthy).
  "Nobody modified this slot" is provable offline, and it is real evidence — a symptom shared by
  vanilla and all mods points at content nobody touched;
- names, bone/track counts, loop flags.

**Denied offline**: rotation. `slot_matrix` / `cmp_slots` / `scan_pose` are float-only (same
gate). If the suspect slot is quantized, any offline pose argument is structurally blind —
**the runtime probe is then not optional but the only way to tie the symptom to the slot**.

**Consequences for the fix**: avoid solving the quantized rotation codec entirely — copy a
proven whole blob from a float slot (`copy_slot_blob.py`); rotation, translation, and skeleton
travel together, zero codec work. Solving the codec (bounds block, then int8-normalized /
bit-packed hypotheses, validated against a float rewrite of the same slot) is a last resort,
only when a pose-level edit of a quantized clip is unavoidable.

## 4. Runtime motion-ID probe (the decisive step)

Call chain, every step with a cited source (a working mod, the engine dump, or the API book) —
never from memory:

```
sdk.get_managed_singleton("<game>.player.PlayerManager")
  :call("findMasterPlayer")                        # plain name; call() takes no parentheses
  :call("get_GameObject")
  :call("getComponent(System.Type)", sdk.typeof("via.motion.Motion"))   # 100+ overloads: full signature required
  :get_Layer()                                     # wrapped container
  :get_Count() / :get_Item(0..n-1)                 # NOT #, NOT ipairs
  layer:getMotionNodeCount()                       # a layer can blend SEVERAL nodes at once
  layer:getMotionNode(i)  for i = 0..count-1       # colon sugar; call() on this InternalCall throws
  node:get_MotionName() / get_MotionID() / get_MotionBankID() / get_Weight()
```

Probe discipline, each line backed by a failure that cost a full in-game round:

- **No home-made guards.** `type(o[name]) ~= "function"` rejects managed methods — `o[name]`
  returns a `REMethodDefinition`, not a Lua function — so `findMasterPlayer` was never actually
  called across eight probe versions while the log looked plausible.
- **Separate "threw" from "returned nil"** in the log; record the error text once, not per frame.
- **Frame numbers must not enter the "has it changed" criterion.** Log a row only when
  the identity **or the quantized weight** changes per layer, or a minute of gameplay produces
  hundreds of thousands of rows (quantize the weight, e.g. to 0.1, or the row rate explodes).
- **Index 0 is the group's first name, not the clip that plays.** A layer holds N nodes blended by
  weight, and **the group's list order decides what index 0 reports**. On the project that produced this
  file the dash group (`plc_*_012_013_038`) reported `012` at weight **0.00** while `038` — third in the
  list — sat at **0.96**; a whole investigation ran on "the dash plays 012" before the weight column was
  read. Report the node count, every node's ID, **and its weight** — the weight is the answer (where a
  build exposes a highest-weight getter, use it as the cross-check). Also note that the group names in the
  data file (`plc_*_A_B_C`) *are* the blend set, so this is checkable offline before any probe run.
- **Marker buttons** ("tag now", "clear") so the user's test flow (normal run → sprint at a large
  monster) is visible in the log; flush on marker and every N frames as a floor.
- **Local stub before deployment.** Simulate the whole chain with scripted scenarios (player not
  ready → acquired → id changes → marker) plus assertions, and a static scan banning every
  pattern that already failed (the guard, double-return-value misuse, sandbox globals, the
  container APIs on the wrong type). **The stub must reproduce managed-object quirks**: a stub
  whose container is a plain Lua table passes `#layers` while the game throws — one probe round
  was wasted exactly this way.
- **Deployment check script** (read-only): mixed-in local-only tools, stale copies differing from
  the repo, project scripts not yet deployed. A fixed repo does not change what the game loads.
- Read the result against the live UI window too: the operator can watch `L1: bank:id:name` **plus each node's weight** in
  the panel while performing the motion and confirm by eye which name corresponds to which gait.

## 5. Criteria methodology — the expensive lessons

1. **Runtime read before offline inference.** The offline criteria were revised four times
   (candidates switched three times); one probe log plus the operator's live observation settled
   it. The probe is cheap; deep offline reasoning on an unverified premise is not.
2. **A relayed attribution is not a constraint.** "Only the reference mod fixed it, so the slot
   must be inside the 14 slots it touches" — the premise (what the reference mod actually fixed)
   was never verified, and the runtime read broke it: the guilty clip was untouched by both mods.
   User observations of mod behavior are leads, not exclusive premises.
3. **"Resembles" ≠ "plays".** Keep the two questions on separate ledgers: pose signature (which
   clip looks like the symptom) and slot routing (which clip the engine plays then). Only the
   second is the answer.
4. **Archive the churn.** Every time a criterion flips a candidate, record the evidence, the
   counter-evidence, and the reason. The archive is what let the final analysis avoid re-walking
   the four earlier rounds.
5. **When the runtime finding contradicts an old constraint**, prefer the runtime read, demote
   the constraint to "unverified attribution", and design a cheap separate experiment for it
   (e.g. run the same probe with the reference mod installed and watch whether the guilty clip
   still plays).
6. **Minimal surgery wins when reusing a clip across slots.** Copying a proven whole blob and
   repointing the slot (keeping the replaced data as an orphan) is byte-precise, avoids codec
   work, and its self-check ("all bytes unchanged except the pointer and the appended region")
   is trivially strong. Rebuilding curves across sources instead re-couples rhythm-critical
   pairs: a Foot_IK world target must keep the same stride rhythm as the root translation it
   rides with, or every footstep drags (~9 cm per step at a 4.4% speed mismatch in the one
   measured case).

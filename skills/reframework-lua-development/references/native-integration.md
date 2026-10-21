# Native integration ladder

When the feature needs something the game already does — quest flow, network sessions, native dialogs, list rendering — start from the native path and add depth only where the previous level is insufficient. Before using a deeper level, be able to say why a shallower one fails.

## Level 0 — Establish the native contract first

Reproduce the flow manually and note entry points, state transitions, and exit conditions. Then probe read-only before writing the feature:

- enumerate a type with `get_methods` / `get_fields` / `get_properties` instead of guessing names or signatures;
- call getters from a frame callback or a temporary hook that only counts calls and samples `this` values — never write files per frame;
- separate observed facts from inference, and record the verified class / method / field / owning manager / valid lifecycle window in project docs. A `snow.*` name that looks similar to another is not the same call chain.

## Level 1 — Call the native method directly

The game can already do it; call it with the same context the native caller prepares. Most failures at this level are missing initialization context, not wrong signatures — compare what the native flow sets before the call (context fields on the manager, flags cleared, prior state cancelled) and replicate that sequence.

## Level 2 — Build the index when no reverse query exists

When the game only maps A→B but the feature needs B→A, join the static data tables in Lua (reward/drop tables → monster or map → quests) instead of reimplementing game logic or scraping UI. Filter out zero-probability table entries and handle fixed-rule exceptions explicitly. Keep static tables separate from per-player dynamic lists — an owned local list and a host's lobby list are different data.

## Level 3 — Snapshot dynamic data, re-verify before acting

Anything displayed from dynamic state (network search results, mutable quest lists) can change before the user acts. Snapshot it with a fingerprint of the fields that define it, and before executing, re-read the authoritative source and compare — a stale reference must fail with a "changed, select again" path, not act on old data. Joining a session may be the only way to obtain the complete identifier; until then, display what the snapshot proves and suppress what it does not.

## Level 4 — Reuse native dialogs and lists

**Native select window**: open it through the GUI manager, drive its input update from the parent's own update path (it has no independent update loop), read result and index, close it, and restore the parent's saved selection index.

**Native list adaptation**: build the model type the native list expects, fill it, and rewrite the existing row widgets (text, play state, visibility) instead of adding new controls. A partial model (for example, `_QuestNo` = 0) is a display shim only — it cannot drive the full detail pane; pass a nil model to suppress the detail view until a real one exists.

**Input ownership** while a custom flow is open: skip the parent state machine's update; ignore input on the frame the dialog opens and the frame it closes (that closing input belongs to the dialog, not the list behind it); restore focus, selection, and original text before resuming the parent.

**Two close paths, not one**: normal close restores everything and restarts the native routine; "closing because the player is departing" must first deactivate the custom mode so a close hook cannot cancel work the departure flow already permitted, and must not restore widgets that are being unloaded anyway.

## Level 5 — Command state machine across frames

UI callbacks never run network or quest operations. A UI click only records `command = { kind = "join", row = row }`; `re.on_pre_application_entry("UpdateBehavior", ...)` consumes commands and advances a phase machine (`context → searching → joining → permission → idle`), with each phase waiting for the native busy flag, callback, or result.

- Wrap each step in `pcall`; on failure, clean up the session/UI state and report — do not leave a half-started native operation.
- Give every phase a timeout, and a cancel command that unwinds from any phase.
- Re-fetch singletons after operations that can change which object a getter returns (starting one session manager can switch what the session-type getter returns).
- Gate a new operation on explicit exclusions: network busy, already in a session, active quest, native matchmaking running, previous request still winding down.

## Level 6 — Conditional hooks on native state machines

The deepest level: hooking a native update/state method and conditionally skipping it, or overwriting its result. Follow the conditional-hook rules in `runtime-and-hooks.md`, and treat every skip as a borrow of the native state machine — restore it on every exit path, and verify the flows that interact with the skip (rapid repeated confirms, other mods injecting the same UI).

## Diagnosing an integration

Maintain a status file (`json.dump_file`) written on phase changes and at a throttled interval — never per frame: script version, tdb version, current phase, counters (checks, matches, input hits per device), and raw evidence (search keys, error codes, session identities). Keep user-facing error text localized and machine evidence raw in the report, so a bug report reproduces the state without a log flood.

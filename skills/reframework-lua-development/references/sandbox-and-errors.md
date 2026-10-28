# Sandbox and load errors

Scope: errors the script itself raises — ScriptRunner popups, red error text, syntax and load
failures, unsupported sandbox facilities, load-contract timing.

Out of scope: anything requiring the runtime timeline to be reconstructed — hook never fired,
reload ordering, repeated framework-level errors, timing and performance. Those belong to
`mod-debugging`. The dividing question: **can the cause be located from the script plus the error
message alone?** If yes, it stays here.

## What the environment provides

The REFramework Lua state is not standard Lua. Check every global and stdlib call against the
target build before relying on it:

- `os.execute` and its siblings are absent — `os` is trimmed;
- `arg` does not exist, so a script must not derive paths from `arg[0]`;
- `io` exists, but `io.open` on a relative path whose directory does not exist returns `nil`
  without raising — no file, no error, no clue;
- `json` is REFramework-provided (`json.dump_file` resolves under `reframework/data/`) and is
  absent in a plain interpreter;
- individual `imgui` bindings vary by nightly — fail a mid-panel call and a required `tree_pop`
  can be skipped, turning a missing widget into an assertion.

The core script-facing globals are all REFramework-provided: `sdk`, `re`, `imgui`, `json`,
`log`, `fs`, and `d2d` where the build offers it. None of them are provided by standard Lua
itself, so "is `log` available?" is an environment question, not a Lua one — confirm
signatures against `reframework-api-reference` instead of recalling them.

Every item above is legal standard Lua. That is precisely why a local interpreter is not evidence:
the code runs on the desktop and fails in the game.

## Read a load failure by its shape

- `attempt to index a nil value (global 'X')` — global `X` does not exist in this build.
- `attempt to call a nil value (global 'X')` — that function does not exist in this build.
- `field 'X' is not callable (a nil value)` — the object exists and that member is `nil`.

These usually mean "the environment does not provide this", not "the logic is wrong". Check the
environment first, then edit logic. When a name is uncertain, enumerate the type definition
(`get_methods` / `get_fields` / `get_properties` + `get_name`) instead of guessing.

## Diagnose in this order

1. Lua syntax — would standard Lua also reject it?
2. Sandbox — is every global and stdlib call it makes provided by the target build?
3. Load contract — does every object it touches exist at that lifecycle point? An unavailable
   singleton at the title screen is a timing fact, not a missing API.
4. Managed layer — type, signature, nullability. See `runtime-and-hooks.md`.

## Do not silence the problem

Wrapping the whole script in `pcall` is not "guarded". A blanket `pcall` turns "the environment
does not provide this" into a silent no-op, which is harder to find than a popup: the feature
simply never works and nothing is reported. Guard the individual calls that may legitimately fail,
and keep a diagnostic path that still reports a miss.

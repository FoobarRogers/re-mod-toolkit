# Structure and delivery

## Separate concerns

- Runtime logic: reads game state and performs the feature.
- UI: displays state and changes user settings; it does not gate runtime behavior unless that is an explicit setting.
- Persistence: owns load, migration, validation, defaults, and save.
- Localization: owns user-facing labels and messages.
- Diagnostics: owns bounded logs and debug-only visibility.

Put autorun entrypoints under the project's declared `reframework/autorun/` layout. Put configuration, caches, and logs under the project's declared `reframework/data/<project>/` layout unless compatibility requires an existing path.

When starting a small script from scratch, prefer a single-file first deliverable that carries only the configuration, callbacks, and UI the requested feature requires; the skeleton below illustrates the components, and not all of them are mandatory. Grow the file in regions: config → state → runtime access → feature logic → hooks → UI → lifecycle.

```lua
log.info("[MyMod] loaded")  -- load marker; version-tag it when deployed as an overlay
local default_config = { enabled = true }
local config = json.load_file("MyMod/config.json") or default_config
-- `or` only covers a missing file; merge per-field defaults when loading configs saved by older versions
local function save_config() json.dump_file("MyMod/config.json", config) end

re.on_frame(function()
    if not config.enabled then return end
end)

re.on_draw_ui(function()
    -- widget signatures vary by nightly; confirm against reframework-api-reference
    if imgui.button("MyMod: toggle") then
        config.enabled = not config.enabled
        save_config()
    end
end)
```

Choose the UI route per feature: `imgui` widgets suit settings panels and state inspection, `d2d.register` suits HUD overlays rendered without a window. The choice is also a measurement boundary — check whether the profiler used for a comparison includes the selected drawing callbacks; keep drawing paths consistent between measurements, and report any work excluded from instrumentation.

Keep local development aids — stubs, fake-object harnesses, self-test scripts — outside the deployed tree, and name them so their status is visible without opening them. Give each one a guard that exits before touching any global if the game loads it by mistake: a harness that replaces `sdk`, `re`, or `imgui` breaks every mod loaded in the same pass, and it does that *before* raising the error that produces the popup — so the popup is the least of the damage. A directory that mixes deployable scripts with local tools silently destroys the invariant "everything here can be copied into autorun"; once that invariant is gone, nothing warns anyone.

Naming can also make the mistake harmless rather than merely visible: autorun loads only `.lua` files, so a local aid named `<name>.lua.local` does not execute even if it lands in autorun. Prefer that over a guard alone — a guard is a runtime backstop, not the first line of defense. When you do enforce a name rule, match the suffix exactly instead of relying on a glob: Windows wildcards match "extension starts with", so `dir *.lua` also lists `x.luat`.

A fix in the repository does not change what the game loads. After changing any deployed script, verify the deployment site itself and reconcile it — which files are present, whether each still matches the repository, which ones should not be there at all. A stale copy left in autorun reproduces the old symptom exactly and makes the repaired code look broken.

When the deployment is an overlay — a mod manager copying folders over one another — add a one-line load marker with a version tag to the script head (`log.info("[MyMod] fix1 loaded")`). Its presence in the framework log confirms that the file carrying that marker won the copy; it does not rule out duplicate or stale scripts elsewhere. Check it before attributing any behavior to your change.

## Configuration

Load once at an appropriate lifecycle point and write only on a meaningful change. Validate types and ranges. Preserve compatible existing values and unknown fields when round-tripping a shared configuration. Do not let a corrupt optional setting prevent the whole script from loading if a safe fallback exists.

## Delivery checks

- The target REFramework build can parse and load the script.
- Potentially absent runtime objects are guarded.
- New hooks have clear activation and restoration behavior.
- UI state does not accidentally start or stop unrelated runtime logic.
- Reset Script does not multiply effects or retain stale references.
- Logs are bounded and useful.
- Test steps cover the lifecycle event affected by the change.

Use a project-provided Lua checker or compatible parser when available. A generic system `luac` may target a different Lua version and is not, by itself, proof of REFramework compatibility.

A local interpreter validates logic, data shapes, and output paths. It cannot validate what the environment provides. List every non-portable facility the script touches and treat each as unverified until the target build loads it — and say that explicitly, rather than reporting "ran fine locally" as verification. See `sandbox-and-errors.md` for the facilities that differ.

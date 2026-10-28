# Runtime objects and hooks

This file is about the objects and callbacks that move. What the Lua state itself provides — which
globals and stdlib calls exist, and how a load failure reads — is covered in `sandbox-and-errors.md`.

## Managed object lifecycle

- Treat singletons, fields, components, and method returns as nullable unless runtime evidence establishes otherwise.
- A managed object may become invalid after loading a save, changing map, entering or leaving a quest, rebuilding MasterPlayer, or resetting scripts.
- A valid managed reference is not proof that it is the current actor. Check authoritative identity separately from object liveness; account for sampled absence and possible address reuse.
- Cache stable identifiers and cheap lookup state longer than managed objects. Document invalidation conditions for any long-lived managed object cache.
- When a reference becomes invalid, clear dependent state before reacquiring it. Do not keep calling an invalid object in a protected loop.

## Working with managed objects

Declare type, method, and field lookups once at the top through one asserting helper, so a missing type or overload fails at load with its name instead of as a nil call mid-feature:

```lua
local function method(type_name, signature)
    return assert(assert(sdk.find_type_definition(type_name), type_name):get_method(signature), signature)
end
```

- Prefer full signatures (`"setSelectIndexAll(System.Int32)"`) so overload resolution is explicit — several native methods share a name across different parameter lists and return types.
- Instance calls are `m.f:call(obj, ...)`; static calls pass `nil` as the instance.
- Arrays are 0-based (`get_size()`, `arr[i]`). REFramework boxes primitive and enum array elements — read the scalar back through the element type's `value__`/`mValue` field; object-typed fields are already scalars.
- Managed collections are called by name (`list:call("get_Count")`, `get_Item`); to copy one out, `get_Values` then `CopyTo` into `sdk.create_managed_array`.
- Construct with `sdk.create_instance` (plus an explicit `.ctor()` when the native type requires it). Small allocations live in the VM temporary pool until `add_ref` promotes them: `add_ref` what must survive the current SDK call or be held across frames, and keep owned references in one table cleared on exit so Lua GC releases them in a predictable order.
- Nullable value-type parameters: take the parameter type from the method's `get_param_types()[i]`, build with `ValueType.new(t)`, then `set_field("_HasValue", true)` / `set_field("_Value", v)`.
- ByRef parameters read a pointer slot, they do not replace it: hold the pointee's address in `sdk.create_uint64(obj:get_address())` and pass `sdk.to_ptr(slot:get_address() + offset)`, with the offset from the wrapper field's `get_offset_from_base()`. Verify pointer level, value lifetime, and call phase for each parameter separately — this is per-method ABI work, not a reusable trick.
- `sdk.create_userdata` loads UserData asynchronously and can expose its array before deserialization fills it: gate first use on a non-empty array whose elements carry the expected fields, and retry on later frames.

## Hook selection

Confirm the declaring type, exact overload, parameter order, return behavior, and call frequency. Establish whether the hook observes, modifies, or replaces behavior.

Use a pre-hook only for work that must happen before the original call. Use a post-hook when the original result or completed state is required. Preserve the original method's semantics unless replacement is the requested feature.

Prefer a method that represents the actual state transition. When no suitable verified transition hook exists, use a bounded current-actor identity check at the cadence required by the feature; per-frame checks can be appropriate for timely reconstruction handling. Do not repeat full player, component, or scene traversal every frame merely because a hook is unavailable. If broader discovery is necessary, budget it explicitly through incremental work or a bounded reconstruction window, and retain a slower recovery path. Never infer event semantics from an open/close method name alone.

## Conditional hooks

When a hook should affect one instance or one UI flow only, gate it instead of matching every call of that method:

- Match `this` by address: `sdk.to_int64(args[2]) == target:get_address()` (with `args[2]` as `this`, converted via `sdk.to_managed_object(args[2])`). Unmatched calls fall through untouched.
- Pass data between the pre and post hook through `thread.get_hook_storage()`, not module globals — nested or reentrant calls would interleave.
- `SKIP_ORIGINAL` replaces native behavior for the matched call only. Skipping a parent state machine's update is how a child dialog takes over input; every skip needs the restore path that hands control back — normal close, scene change, script reset, and the success path itself.
- Wrap Lua business logic inside a hook body in `pcall` — an escaping error aborts the native call chain. On failure, cancel pending work and restore native state rather than leaving the flow half-taken-over.
- Keep structural changes out of the hook stack: set a pending flag in the hook and do the work in a frame callback or `re.on_pre_application_entry("UpdateBehavior", ...)`.
- Overwriting a return value changes state other systems read. Reserve it for a narrowly matched, proven problem, and verify every path that resets the underlying state — disconnect, scene change, cancellation.
- `sdk.hook_vtable` targets one object's vtable entry; confirm its actual scope on the target build before assuming other instances are unaffected.

## Per-frame cost model

A frame callback or hot hook runs at a cadence set by the game or framework — that part is
not yours to optimize. Distinguish the invocation frequency from the frequency of
substantive work: where the feature permits, skip unchanged work or run expensive checks
less often, without changing required response timing. What you control is how many
Lua→native bridge calls (`get_field`, `call`, `get_address`, `to_managed_object`…) each
pass performs. Bridge-call count is a useful estimate of workload, not a direct measure of
execution time — compare call types and frequencies, then verify total cost with profiling.
As an arithmetic example, reading three fields from each of fourteen objects requires about
42 field reads per pass, excluding lookup and conversion work; a steady poll of that shape
is a first-class frame-budget consumer even when each call is individually cheap, and it
can rank among the most expensive scripts in a loaded set without containing a single
"slow" call.

Estimate the bridge-call count of a designed pass before writing it, and verify with a
profiler afterwards. Do not spend the budget discovering what has not changed.

## Hot paths

Do not perform these in a high-frequency hook or frame callback:

- filesystem reads or writes;
- JSON encoding or decoding;
- repeated full object or component scans;
- unbounded log output;
- UI construction unrelated to the callback;
- repeated type or method discovery that can be cached safely.

Throttle diagnostic logging and make it removable or disabled by default in delivered builds.

## Reload safety

Keep initialization idempotent where possible. Separate immutable definitions from mutable runtime state. Reset caches, transition state, and pending work on script reset. When a hook cannot be unregistered, avoid adding another identical hook during the same script lifetime and design the hook body to consult current module state rather than captured stale state.

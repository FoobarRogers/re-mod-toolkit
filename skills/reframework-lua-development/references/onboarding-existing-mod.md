# Onboarding an existing mod

Apply these rules when the task is to modify, fix, or optimize a script whose runtime
structure and design assumptions have not yet been established in the current task —
especially one that has already passed through several rounds of fixes (human or AI) before
you reached it.

## Map the script before touching it

Answer four questions from the source before restructuring anything:

1. Which variables hold the runtime state?
2. Which callback or hook actually drives the behavior?
3. When is configuration loaded and saved?
4. At which lifecycle points can the game objects it touches be rebuilt?

Support each answer with the relevant source locations, and where source alone cannot
settle it, with runtime or API evidence; record unresolved points explicitly. Do not
restructure before these four have evidence-backed answers.

## Recognize symptom patches

Repeated compensation logic may indicate patches stacked on an unresolved root cause, but
these mechanisms can also be required by the runtime contract; treat them as investigation
cues, not as proof of a defect:

- fingerprints or signature checks whose only job is to notice "something changed";
- forced rescan flags and magic-number refresh windows (`*_FAST_REBUILD_FRAMES = 60`);
- accelerations that exist to shrink the delay between a game-side change and this
  script's next re-apply.

Each such patch typically buys a shorter detection window. Find the root cause it
compensates for first: an incorrect upstream condition can make the whole detection network
redundant. Before removing patches, establish that relationship, write down the correctness
argument for why they become redundant (what re-asserts the state, and how long a game-side
reset can survive), and put the measured cost of both designs side by side.

## Check coexistence on shared surfaces

Before delivery, check whether other installed mods hook the same methods or write the
same properties. Two mods polling the same manager once per frame is not automatically a
defect — decide by measured magnitude, not by pattern matching. Where two mods provide the
same feature, redundancy is a user choice to surface, not a bug to silently "fix".

## Gate optimization on magnitude

Profile before proposing to optimize. State current cost and expected gain in per-frame
terms, and do not justify a performance-only rework by gains the measurement cannot
reliably distinguish.
Split a proposal into what is certain (removing measured calls) and what is a candidate
(an assumed-cheaper alternative path); a candidate stays unverified until measured in
game.

## Verify the deployment, not just the repository

A fixed file in the repository does not change what the game loads; overlay deployments
add copy-order ambiguity on top. The load marker in `structure-and-delivery.md` is the
cheap discriminator: before attributing any behavior to your change, confirm from the
framework log that the file you edited is the file the game loaded.

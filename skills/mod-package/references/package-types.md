# Package types

Project rules override these defaults.

| Type | Typical contents | Must not imply |
| --- | --- | --- |
| test | minimal changed files needed to evaluate an experiment | acceptance, main promotion, or release readiness |
| fix | minimal changed files needed to verify a targeted correction | that unrelated defects are resolved |
| release | complete installable set from an approved main state | permission to publish unless separately authorized |
| prerelease | complete, clean-installable file set frozen as the working baseline | a final release; acceptance as a working baseline does not imply release criteria are met; the `prerelease` mark must stay in the label |
| add-on | only the files that swap the shipped release's feature A to feature B（A/B 功能替换包，非 Lua mod 常见） | a baseline version bump or a complete standalone package |

## Test and fix packages

Keep the package incremental when the project uses an already-installed baseline. Include the baseline requirement, exact replacement paths, expected observation, and rollback instructions. Do not silently add a complete `Mods` package, downloads copy, or release directory when the project reserves those for approved releases.

## Release packages

Build from the approved source state, not from an arbitrary working directory. Include all runtime files required for a clean install and exclude tests, temporary outputs, raw research data, logs, backups, and development-only tools unless the release contract names them.

Verify the archive after creation. A successful ZIP command does not establish that the package layout or file set is correct.

## Prerelease packages

A prerelease freezes a candidate the user accepted as the working baseline for ongoing fix/test work: build it as a complete, clean-installable file set, place it in the release folder, and keep the `prerelease` mark in the label（如 `1.11prerelease1`）so it stays distinguishable from the final release（`1.11`）. Acceptance as a working baseline does not imply that all release criteria have been met; a prerelease is not a release and carries no publish authorization; baseline registration is owned by the version workflow.

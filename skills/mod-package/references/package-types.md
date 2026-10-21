# Package types

Project rules override these defaults.

| Type | Typical contents | Must not imply |
| --- | --- | --- |
| test | minimal changed files needed to evaluate an experiment | acceptance, main promotion, or release readiness |
| fix | minimal changed files needed to verify a targeted correction | that unrelated defects are resolved |
| release | complete installable set from an approved main state | permission to publish unless separately authorized |

## Test and fix packages

Keep the package incremental when the project uses an already-installed baseline. Include the baseline requirement, exact replacement paths, expected observation, and rollback instructions. Do not silently add a complete `Mods` package, downloads copy, or release directory when the project reserves those for approved releases.

## Release packages

Build from the approved source state, not from an arbitrary working directory. Include all runtime files required for a clean install and exclude tests, temporary outputs, raw research data, logs, backups, and development-only tools unless the release contract names them.

Verify the archive after creation. A successful ZIP command does not establish that the package layout or file set is correct.

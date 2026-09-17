# Status

## Current focus

The `rewrite/dev-server-v1` branch has been reset for a ground-up Kyth implementation.

## Current state

- replacement architecture is defined in `DESIGN.md`;
- concrete V1 runtime/reload behavior is specified in `notes/design/v1-protocol.md`;
- implementation sequencing is defined in `PLAN.md`;
- the previous Python implementation, tests, generated lockfile, and architecture-specific tooling have been removed from this branch;
- obsolete generic testing notes and the accidentally committed Rope database have been removed;
- `POLICY.md` remains the repository documentation policy;
- no executable Kyth package currently exists on this branch.

## Next boundary

Begin Phase 1 from `PLAN.md`: establish the minimal package/tooling scaffold and implement the supervisor-owned socket plus restartable ASGI child lifecycle before adding filesystem or browser behavior.

## Known gaps

- no package metadata or dependency lock exists yet;
- no source or tests exist yet;
- exact cross-platform socket-passing support is not yet implemented or validated;
- browser protocol and provenance behavior are design-only until later plan phases.

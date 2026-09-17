# Kyth

Kyth is a local development supervisor for Python web applications and generated websites. It restarts server code safely, keeps the public listening socket stable across restarts, and will update only browser views affected by changed content when dependency information is available.

The ground-up V1 implementation is in progress. Phase 1 provides the supervisor-owned application socket, restartable ASGI child lifecycle, explicit readiness reporting, bounded shutdown, failure recovery, generation state, and the initial `kyth package.module:app` CLI. Filesystem watching and browser synchronization begin in later phases.

See:

- `DESIGN.md` for project architecture and invariants;
- `notes/design/v1-protocol.md` for concrete V1 runtime and reload behavior;
- `PLAN.md` for implementation sequencing;
- `STATUS.md` for current project state;
- `TODO.md` for immediate work.

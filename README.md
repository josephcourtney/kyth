# Kyth

Kyth is a local development supervisor for Python web applications and generated websites. It restarts server code safely, keeps the public listening socket stable across restarts, and updates only browser views affected by changed content when dependency information is available.

The `rewrite/dev-server-v1` branch is a ground-up replacement of the original implementation. It currently contains the replacement design and implementation plan but no executable implementation.

See:

- `DESIGN.md` for project architecture and invariants;
- `notes/design/v1-protocol.md` for concrete V1 runtime and reload behavior;
- `PLAN.md` for implementation sequencing;
- `STATUS.md` for current project state;
- `TODO.md` for immediate work.

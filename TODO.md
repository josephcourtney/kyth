# TODO

- create the minimal Python package and `pyproject.toml` for the Phase 1 vertical slice;
- add only the runtime dependencies required for ASGI child execution and the initial CLI;
- define supervisor and child state types from `notes/design/v1-protocol.md`;
- bind the application socket in the supervisor and pass it to a child process;
- run a minimal ASGI target on the inherited socket without Uvicorn reload mode;
- add an explicit child readiness channel that signals only after ASGI lifespan startup;
- implement bounded graceful shutdown and escalation;
- add lifecycle tests covering repeated restart, startup failure, recovery, and stable port ownership;
- establish lint, type-check, and test commands only after the initial scaffold exists.

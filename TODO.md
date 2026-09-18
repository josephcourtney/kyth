# TODO

- implement Phase 3 supervisor-owned browser control service independent of the restartable ASGI child;
- add a local-only SSE endpoint carrying structured events and generation identifiers;
- add a browser registration/update endpoint and in-memory active-view records;
- generate a per-session unguessable control token and enforce appropriate origin restrictions;
- define reconnect/sync behavior without introducing browser reloads yet;
- expire inactive views after a configurable interval;
- add protocol tests independent of any application framework;
- add lifecycle coverage proving the control service remains available while the application child restarts;
- run `just check` and resolve any platform/toolchain issues exposed by Phase 2.

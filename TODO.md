# TODO

- implement Phase 4 transparent browser-client injection at the ASGI HTML-response boundary;
- serve the external development client from the supervisor-owned control service;
- inject the control URL, session token, current render/document identity, and generation without application changes;
- register one tab-scoped view and open its SSE connection from the injected client;
- implement generation-aware full-page reload handling with duplicate-event protection;
- update content length/cache validators correctly for modified HTML responses and document the streaming-response fallback;
- ensure compressed HTML is either made injectable before transformation or passed through conservatively;
- connect successful Python restart to a readiness-gated `reload` event rather than only a `sync` event;
- add system coverage for `change -> restart -> readiness -> reload` while preserving the control connection;
- run `just check` and resolve any platform/toolchain issues exposed by Phase 3.

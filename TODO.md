# TODO

- implement Phase 7 render provenance API independent of any specific template engine;
- associate opaque render identities with source dependency sets and source versions;
- implement the first Jinja adapter without requiring normal application-source changes where practical;
- capture Jinja inheritance, includes, imports, and runtime-selected template dependencies where feasible;
- invalidate only active renders that depend on a changed template;
- retain conservative route/application-scope reload when runtime dependency capture is incomplete;
- add tests proving an unrelated template change does not disturb the active view while a shared-template change does;
- preserve the Phase 1-6 zero-touch fallback when no template adapter applies;
- run `just check` and resolve any platform/toolchain issues exposed by Phase 6.

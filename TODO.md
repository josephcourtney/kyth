# TODO

- implement Phase 5 direct static/generated HTML awareness;
- associate active views with directly served document/output identities where this can be inferred without framework-specific integration;
- separate source/output invalidation from browser action in executable code rather than only the design model;
- avoid reloading a view for a known unrelated HTML output change;
- retain conservative full reload for ambiguous relationships;
- keep inactive outputs logically stale without forcing eager browser work;
- add tests with multiple active views proving that only views displaying an affected direct output reload;
- preserve the Phase 4 full-reload fallback whenever direct mapping is unavailable;
- run `just check` and resolve any platform/toolchain issues exposed by Phase 4.

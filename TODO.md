# TODO

- implement Phase 2 filesystem observation with `watchfiles` using configured watched roots and ignored paths;
- normalize create/modify/delete events into deterministic logical batches;
- implement default path classification separately from watcher mechanics;
- connect restart-requiring batches to `Supervisor.restart_child()` without moving lifecycle policy into the watcher;
- coalesce edits that arrive during startup or shutdown so they cause at most one necessary follow-up restart;
- add concise change/restart decision logging;
- add tests for deterministic batches, ignored paths, restart classification, and restart coalescing;
- run `just check` and resolve any platform/toolchain issues exposed by the Phase 1 implementation.

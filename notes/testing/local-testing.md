# Local Testing Guide (no CI)

This page distills the **local testing** workflows that implement the broader testing strategy in `notes/TESTING.md` and `notes/testing/README.md`. The focus here is practical: how to run the suites locally and how to use the helper fixtures that enforce the concurrency and subprocess robustness rules from the plan.

## Command map

| Command | Description |
| --- | --- |
| `just test` | Run the entire suite (`tests/`, all markers) with coverage. This is the “CI-equivalent” command for your machine. |
| `just test-fast` | Run `pytest -m "unit and not slow"`. Use this after edits to `src/` or during development for fast feedback. |
| `just test-marker "<marker>"` | Run a custom marker expression while tolerating “no tests collected” (exit status 5). Useful for component/integration/regression subsets without editing `justfile`. |

Additional adapters:

* `just lint` / `just format` / `just typecheck` - keep lint/type running before a full suite.
* `just test-timed` - generate a `--durations=25` report when diagnosing slow runners.

## Marker conventions

The repository uses the `pytest-test-categories` plugin to label runtime budgets. In addition to the strict scope markers listed in `notes/TESTING.md`, tests can also carry the plugin-provided size markers `small`, `medium`, `large`, and `xlarge` to express their expected duration or resource footprint. These markers do not replace the required scope (`unit`, `component`, etc.) but can be combined with them (e.g., `@pytest.mark.unit @pytest.mark.small`) so the plugin can filter by size without altering the strict-marker enforcement.

## Concurrency helpers (per the local plan)

All local tests can import `thread_coordinator`, `async_deadline`, and `subprocess_runner` from `tests/conftest.py`:

| Fixture | Purpose |
| --- | --- |
| `thread_coordinator` | Provides a mini thread pool, explicit barriers, queue drains, and deadline-aware `wait()` so synchronous concurrency tests obey **deadline** and **causality** rules. Each submission re-raises exceptions, and a `faulthandler` guard dumps stacks on hang. |
| `async_deadline` | Wrap every awaited background operation with `await async_deadline(coro, timeout=...)` so async tests remain deterministic. |
| `subprocess_runner` | Run short-lived binaries with captured stdout/stderr, enforced timeouts, and deterministic working directories. Use this fixture any time a test exercises subprocess interactions or pipe-based protocols. |

## Applying the concurrency principles locally

1. **Assert causality, not timing** - use `thread_coordinator.barrier()` or `subprocess_runner` to enforce ordering before asserting. Avoid arbitrary `time.sleep`.
2. **Deadline every wait** - the helpers default to a 1 s timeout. Call `.wait(timeout=)` or `await async_deadline(..., timeout=...)` explicitly if the scenario needs more time.
3. **Propagate exceptions** - always inspect futures from `thread_coordinator.submit(...)` via `.wait()` so thread failures bubble to pytest.
4. **Control the scheduler** - for stress runs, wrap repeated `thread_coordinator` interactions inside loops and optionally adjust `sys.setswitchinterval(...)` locally before `thread_coordinator.submit()` to inject jitter.
5. **Test logic separately** - move pure logic into functions under test and use the fixtures only in thin integration layers that glue threads, async tasks, or subprocesses.

## Subprocess + pyfakefs guidance

* Prefer **Pattern A** from the plan: keep “external programs” behind in-process fakes that consume `queue.Queue` or `os.pipe()` pairs. The `subprocess_runner` fixture still helps by capturing pipes for those fakes.
* When you must run a real binary, wrap the section with `fs.pause()` / `fs.resume()` (pyfakefs) and materialize the inputs into a real `tmp_path`. After the subprocess finishes, import the outputs via `fs.add_real_file(...)` as described in `notes/testing/README.md`.
* Always drain both `stdout` and `stderr` (the runner raises on non-zero exit and returns both streams) and kill the process group in `finally` blocks if tests spawn long-lived jobs.

## Local robustness checklist

- [x] No raw `sleep()` in concurrency tests; use barriers/events/queues.
- [x] Every join/wait has a timeout (use the fixtures' defaults or pass a `timeout` argument).
- [x] All background work is awaited (`thread_coordinator.wait()` or `await async_deadline(...)`).
- [x] Subprocess interactions go through `subprocess_runner` so stdout/stderr are captured and the child is cleaned up.
- [x] Executors and helpers are context-managed so resources stop before `pytest` tears down the test.
- [x] All new tests reference their scope marker (`unit`, `component`, etc.) following `notes/testing/TESTING.md`.

## Tracing coverage to the plan

For a deeper explanation of why the fixtures exist and how they map to the lifecycle rules, read `notes/TESTING.md` and the Level L3 documents under `notes/testing/`. Use this local guide for day-to-day work and escalate to the broader docs when you need CI-level gating, mutation targets, or compliance workflows.

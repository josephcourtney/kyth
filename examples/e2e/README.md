# Kyth end-to-end example projects

These projects are manual field-test applications for Kyth. They are deliberately separate from the synthetic acceptance fixtures under `tests/`: each directory can be used like a small independent project, with the working directory set to that project.

Use the repository environment without turning `examples/` into a workspace:

```console
cd examples/e2e/plain_asgi
uv run --project ../../.. kyth app:app --verbose
```

Open the printed application URL in a local browser. The control plane is loopback-only, so use a browser on the same machine as Kyth.

## Matrix

| Project | Primary surface |
| --- | --- |
| `plain_asgi` | ordinary ASGI restart, direct CSS/image updates, JavaScript reload fallback, multiple routes/tabs |
| `jinja_site` | zero-touch Jinja render provenance, inheritance, includes, shared vs route-local template changes |
| `generated_site` | version-1 source→output manifest, stale-output deferral, partial generated rebuilds |
| `streaming_site` | explicit `client_script()` integration for streaming and gzip-encoded HTML |
| `integration_api` | explicit render/data dependencies, semantic data updates, readiness checks, reload state preservation |

Each project has its own README with concrete edits and expected behavior.

## Common field-test pass

For each project, exercise a normal editing session rather than only launching it:

1. Open at least two routes or tabs where the project provides them.
2. Make the narrow resource/template/data edit described by the project and verify only the intended browser action occurs.
3. Edit `app.py` and verify a server restart produces a coherent browser generation.
4. Introduce a temporary Python syntax error, save it, then repair it; the browser must recover without restarting Kyth itself.
5. Duplicate a tab and verify the two browser views continue to synchronize independently.
6. Make two quick successive edits and confirm the final browser state matches the files on disk.
7. Stop Kyth with Ctrl-C and verify the process exits cleanly.

Run with `--verbose` when diagnosing a surprise. Record unexplained behavior as a concrete issue rather than changing Kyth speculatively.

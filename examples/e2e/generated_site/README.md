# Generated-site manifest field test

Run from this directory:

```console
uv run --project ../../.. kyth app:app \
  --watch . \
  --watch public \
  --manifest kyth-manifest.json \
  --verbose
```

The second watch root is intentional: the application mounts `public/` at URL root, so it also gives Kyth an unambiguous direct-resource root for URLs such as `/site.css` while `--watch .` keeps source and generator changes under observation.

Open `/` and `/notes/` in separate tabs. Rebuild outputs in another terminal with:

```console
uv run --project ../../.. python build.py all
```

Exercise these edits:

- edit `content/home.txt` but do not rebuild: the home output becomes stale and the browser should not navigate yet;
- run `python build.py home`: only `/` should reload after `public/index.html` changes;
- repeat with `content/notes.txt` and `python build.py notes`;
- edit `build.py`: both declared outputs become stale; rebuild only one target first and confirm the sibling remains deferred until its own output is rebuilt;
- edit `public/site.css`: active pages should receive the direct stylesheet update without a generated-page rebuild.

# Explicit integration API field test

Run from this directory:

```console
uv run --project ../../.. kyth app:app --restart-on ready.flag --verbose
```

Open `/` and `/other` in separate tabs.

This project exercises the documented public integration APIs and browser events:

- `/` calls `depend_on(content/page.txt)` and `depend_on_data("counter", data/counter.json)`;
- a `kyth:data-update` listener claims the `counter` update and refreshes only the displayed value;
- `register_readiness_check()` reads `ready.flag` after child startup;
- `kyth:before-reload` and `kyth:restore-state` preserve the draft input across a server restart.

Exercise these edits:

1. Change `content/page.txt`: `/` should reload while `/other` remains current.
2. Change the numeric value in `data/counter.json`: `/` should update the counter without document navigation.
3. Type text into the draft input, then edit `app.py`: after the restart/reload, the draft should be restored.
4. Change `ready.flag` from `ready` to `blocked`: the restart should fail readiness and the browser should receive a non-navigating server error. Change it back to `ready` to recover without restarting Kyth.

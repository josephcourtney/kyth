# Jinja provenance field test

Run from this directory with Jinja supplied only to this command:

```console
uv run --project ../../.. --with jinja2 kyth app:app --verbose
```

Open `/` and `/about` in separate tabs.

Exercise these edits:

- change `templates/_home_panel.html`: only the home view should reload;
- change `templates/about.html`: only the about view should reload;
- change `templates/base.html`: both views should reload because both renders inherited it;
- change `static/site.css`: both tabs should update styling without navigation;
- edit `app.py`: the child should restart and both pages should move to the new generation.

No calls to `depend_on()` are made here: precision should come from Kyth's zero-touch Jinja tracing.

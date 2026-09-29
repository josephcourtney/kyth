# Plain ASGI field test

Run from this directory:

```console
uv run --project ../../.. kyth app:app --verbose
```

Open `/` and `/about` in separate tabs.

Exercise these edits:

- change `static/site.css`: both tabs should update styling without document navigation;
- change `static/badge.svg`: the home-page image should update in place;
- change `static/app.js`: the page using it should fall back to a full reload;
- change a string in `app.py`: Kyth should restart the application child and reload both routes coherently;
- temporarily introduce a syntax error in `app.py`, then repair it: Kyth should report the failed restart and recover on the next valid edit.

This project uses no Kyth-specific Python integration API.

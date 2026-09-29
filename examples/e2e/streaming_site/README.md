# Streaming and encoded HTML field test

Run from this directory:

```console
uv run --project ../../.. kyth app:app --verbose
```

Open `/stream` and `/gzip` in separate tabs.

Both routes call `kyth.injection.client_script()` before response headers are committed. `/stream` then sends the document in multiple ASGI body chunks; `/gzip` compresses the completed document and returns `Content-Encoding: gzip`.

Exercise these edits:

- change `static/site.css`: both synchronized documents should update styling without navigation;
- edit `app.py`: Kyth should restart the child and both explicitly integrated documents should reload;
- verify the `/gzip` response remains encoded and readable rather than being decompressed or rewritten by Kyth;
- temporarily remove the `client_script()` call and observe that streaming/encoded HTML becomes intentionally pass-through and unsynchronized.

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).parent
CONTENT = ROOT / "content"
PUBLIC = ROOT / "public"


def render(title: str, text: str) -> str:
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <link rel="stylesheet" href="/site.css">
</head>
<body>
  <nav><a href="/">Home</a> <a href="/notes/">Notes</a></nav>
  <main><h1>{title}</h1><p>{text}</p></main>
</body>
</html>
"""


def build(target: str) -> None:
    PUBLIC.mkdir(exist_ok=True)
    if target in {"home", "all"}:
        text = (CONTENT / "home.txt").read_text(encoding="utf-8").strip()
        (PUBLIC / "index.html").write_text(render("Home", text), encoding="utf-8")
    if target in {"notes", "all"}:
        text = (CONTENT / "notes.txt").read_text(encoding="utf-8").strip()
        (PUBLIC / "notes.html").write_text(render("Notes", text), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", choices=("home", "notes", "all"), nargs="?", default="all")
    args = parser.parse_args()
    build(args.target)


if __name__ == "__main__":
    main()

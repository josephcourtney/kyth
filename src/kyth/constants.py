from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent

DEFAULT_HOST = "127.0.0.1"
DEFAULT_HTTP_PORT = 8000
DEFAULT_WS_PORT = 8765

DEVCLIENT_PATH = "/__devclient__.js"
WS_PATH = "/__devws__"

WATCH_EXTENSIONS = {
    ".html",
    ".htm",
    ".css",
    ".js",
    ".mjs",
    ".cjs",
    ".jsx",
    ".ts",
    ".tsx",
    ".json",
    ".map",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".webp",
    ".ico",
    ".txt",
    ".xml",
    ".wasm",
}

IGNORED_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "env",
    "node_modules",
}

DEBOUNCE_SECONDS = 0.15
SHUTDOWN_GRACE_SECONDS = 0.25
GLOB_CHARS = "*?["

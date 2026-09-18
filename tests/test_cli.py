from pathlib import Path

import pytest

from kyth.cli import _parser


@pytest.mark.unit
@pytest.mark.small
def test_parser_accepts_target_host_port_and_watch_paths() -> None:
    args = _parser().parse_args(
        [
            "package.module:app",
            "--host",
            "127.0.0.2",
            "--port",
            "4321",
            "--watch",
            "src",
            "--watch",
            "templates",
            "--ignore",
            "generated",
        ]
    )

    assert args.app == "package.module:app"
    assert args.host == "127.0.0.2"
    assert args.port == 4321
    assert args.watch_roots == [Path("src"), Path("templates")]
    assert args.ignored_paths == [Path("generated")]

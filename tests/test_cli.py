import logging
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from kyth.cli import _configure_logging, _parser, _resolve_app_dir, _resolve_python


@pytest.mark.unit
@pytest.mark.small
def test_parser_accepts_target_host_port_watch_paths_and_control_port() -> None:
    args = _parser().parse_args([
        "package.module:app",
        "--verbose",
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
        "--manifest",
        "build/kyth-manifest.json",
        "--restart-on",
        "config/*.yaml",
        "--external-hmr-on",
        "frontend/*.js",
        "--fallback-scope",
        "templates/admin/**",
        "/admin/**",
        "--fallback-scope",
        "content/docs/**",
        "/docs/**",
        "--control-port",
        "8765",
    ])

    assert args.app == "package.module:app"
    assert args.verbose is True
    assert args.host == "127.0.0.2"
    assert args.port == 4321
    assert args.watch_roots == [Path("src"), Path("templates")]
    assert args.ignored_paths == [Path("generated")]
    assert args.manifest_paths == [Path("build/kyth-manifest.json")]
    assert args.restart_patterns == ["config/*.yaml"]
    assert args.external_hmr_patterns == ["frontend/*.js"]
    assert args.fallback_scopes == [
        ["templates/admin/**", "/admin/**"],
        ["content/docs/**", "/docs/**"],
    ]
    assert args.control_port == 8765


@pytest.mark.unit
@pytest.mark.small
@pytest.mark.parametrize(("verbose", "kyth_level"), [(False, logging.INFO), (True, logging.DEBUG)])
def test_configure_logging_keeps_root_at_info_and_scopes_debug_to_kyth(
    *,
    verbose: bool,
    kyth_level: int,
) -> None:
    kyth_logger = Mock()
    with (
        patch("kyth.cli.logging.basicConfig") as basic_config,
        patch("kyth.cli.logging.getLogger", return_value=kyth_logger) as get_logger,
    ):
        _configure_logging(verbose=verbose)

    basic_config.assert_called_once_with(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    get_logger.assert_called_once_with("kyth")
    kyth_logger.setLevel.assert_called_once_with(kyth_level)


@pytest.mark.component
@pytest.mark.medium
def test_environment_resolution_discovers_venv_and_src_package(tmp_path: Path) -> None:
    python = tmp_path / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    package = tmp_path / "src" / "haint"
    package.mkdir(parents=True)

    assert _resolve_python(None, tmp_path) == python
    assert _resolve_app_dir(None, tmp_path, "haint.server:app") == tmp_path / "src"
    assert _resolve_app_dir(None, tmp_path, "other.server:app") == tmp_path
    assert _resolve_app_dir(tmp_path, tmp_path, "haint.server:app") == tmp_path


@pytest.mark.unit
@pytest.mark.small
def test_parser_accepts_application_environment_overrides() -> None:
    args = _parser().parse_args([
        "haint.server:app", "--python", ".venv/bin/python", "--app-dir", "src"
    ])
    assert args.python == Path(".venv/bin/python")
    assert args.app_dir == Path("src")

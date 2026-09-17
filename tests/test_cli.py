import pytest

from kyth.cli import _parser


@pytest.mark.unit
@pytest.mark.small
def test_parser_accepts_target_host_and_port() -> None:
    args = _parser().parse_args(["package.module:app", "--host", "127.0.0.2", "--port", "4321"])

    assert args.app == "package.module:app"
    assert args.host == "127.0.0.2"
    assert args.port == 4321

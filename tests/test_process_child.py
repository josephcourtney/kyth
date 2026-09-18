from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest
import uvicorn

import kyth.process.child as child
from kyth.process.readiness import ChildCommand, GenerationApplied, GenerationUpdate, StartupEvent

if TYPE_CHECKING:
    from multiprocessing.connection import Connection

    from kyth.injection import ASGIApp, HTMLInjectionMiddleware


class _Control:
    def __init__(self, commands: list[object]) -> None:
        self.commands = commands

    def recv(self) -> object:
        if not self.commands:
            raise EOFError
        return self.commands.pop(0)


class _Readiness:
    def __init__(self) -> None:
        self.sent: list[object] = []

    def send(self, value: object) -> None:
        self.sent.append(value)


class _Injection:
    def __init__(self) -> None:
        self.generations: list[int] = []

    def set_generation(self, generation: int) -> None:
        self.generations.append(generation)


@pytest.mark.component
@pytest.mark.small
def test_control_watcher_applies_generation_then_shutdown() -> None:
    server = cast("uvicorn.Server", SimpleNamespace(should_exit=False))
    control = cast("Connection", _Control([GenerationUpdate(4), ChildCommand.SHUTDOWN]))
    readiness = cast("Connection", _Readiness())
    injection = cast("HTMLInjectionMiddleware", _Injection())

    child._watch_control(server, control, readiness, injection)

    assert cast("_Injection", injection).generations == [4]
    assert cast("_Readiness", readiness).sent == [GenerationApplied(4)]
    assert server.should_exit


@pytest.mark.component
@pytest.mark.small
def test_control_watcher_treats_channel_eof_as_shutdown() -> None:
    server = cast("uvicorn.Server", SimpleNamespace(should_exit=False))

    child._watch_control(
        server,
        cast("Connection", _Control([])),
        cast("Connection", _Readiness()),
        cast("HTMLInjectionMiddleware", _Injection()),
    )

    assert server.should_exit


@pytest.mark.unit
@pytest.mark.small
def test_load_application_resolves_nested_callable(monkeypatch: pytest.MonkeyPatch) -> None:
    def application(*_args: object, **_kwargs: object) -> None:
        return None

    module = SimpleNamespace(nested=SimpleNamespace(app=application))
    monkeypatch.setattr(child.importlib, "import_module", lambda _name: module)

    loaded = child._load_application("example:nested.app")

    assert loaded is cast("ASGIApp", application)


@pytest.mark.unit
@pytest.mark.small
@pytest.mark.parametrize("target", ["example", ":app", "example:"])
def test_load_application_rejects_malformed_target(target: str) -> None:
    with pytest.raises(ValueError, match="invalid ASGI import target"):
        child._load_application(target)


@pytest.mark.unit
@pytest.mark.small
def test_load_application_rejects_non_callable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        child.importlib,
        "import_module",
        lambda _name: SimpleNamespace(app=42),
    )

    with pytest.raises(TypeError, match="ASGI target is not callable"):
        child._load_application("example:app")


@pytest.mark.component
@pytest.mark.small
def test_readiness_server_reports_only_first_startup_event() -> None:
    readiness = _Readiness()
    server = child._ReadinessServer(
        uvicorn.Config(cast("ASGIApp", lambda *_args, **_kwargs: None)),
        cast("Connection", readiness),
    )

    server._report(StartupEvent.ready())
    server._report(StartupEvent.failed("ignored"))

    assert readiness.sent == [StartupEvent.ready()]

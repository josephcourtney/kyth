from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from kyth.process.manager import ChildProcess
from kyth.process.readiness import (
    ChildCommand,
    GenerationApplied,
    GenerationUpdate,
    StartupEvent,
)

if TYPE_CHECKING:
    from multiprocessing.connection import Connection
    from multiprocessing.process import BaseProcess

_EOF = object()


class _Connection:
    def __init__(
        self,
        *,
        received: list[object] | None = None,
        polls: list[bool] | None = None,
    ) -> None:
        self.received = list(received or [])
        self.polls = list(polls or [])
        self.sent: list[object] = []
        self.closed = False

    def poll(self, _timeout: float) -> bool:
        if self.polls:
            return self.polls.pop(0)
        return bool(self.received)

    def recv(self) -> object:
        if not self.received:
            raise EOFError
        value = self.received.pop(0)
        if value is _EOF:
            raise EOFError
        return value

    def send(self, value: object) -> None:
        self.sent.append(value)

    def close(self) -> None:
        self.closed = True


class _Process:
    pid = 1234

    def __init__(self, *, alive: bool = True, exitcode: int | None = 0) -> None:
        self.alive = alive
        self.exitcode = exitcode
        self.terminate_called = False
        self.kill_called = False
        self.closed = False
        self.join_timeouts: list[float] = []

    def is_alive(self) -> bool:
        return self.alive

    def join(self, timeout: float) -> None:
        self.join_timeouts.append(timeout)
        if self.kill_called:
            self.alive = False

    def terminate(self) -> None:
        self.terminate_called = True

    def kill(self) -> None:
        self.kill_called = True

    def close(self) -> None:
        self.closed = True


def _child_process(
    process: _Process,
    readiness: _Connection,
    control: _Connection | None = None,
) -> ChildProcess:
    manager = ChildProcess()
    manager._process = cast("BaseProcess", process)
    manager._readiness = cast("Connection", readiness)
    manager._control = cast("Connection", control or _Connection())
    return manager


@pytest.mark.component
@pytest.mark.small
def test_wait_for_startup_accepts_ready_event() -> None:
    manager = _child_process(
        _Process(),
        _Connection(received=[StartupEvent.ready()]),
    )

    result = manager.wait_for_startup(1.0)

    assert result.ready
    assert result.error is None


@pytest.mark.component
@pytest.mark.small
def test_wait_for_startup_rejects_invalid_event() -> None:
    manager = _child_process(
        _Process(exitcode=7),
        _Connection(received=["not-a-startup-event"]),
    )

    result = manager.wait_for_startup(1.0)

    assert not result.ready
    assert result.error == "child sent an invalid startup event"
    assert result.exit_code == 7


@pytest.mark.component
@pytest.mark.small
def test_wait_for_startup_reports_readiness_eof() -> None:
    manager = _child_process(
        _Process(exitcode=3),
        _Connection(received=[_EOF]),
    )

    result = manager.wait_for_startup(1.0)

    assert not result.ready
    assert result.error == "child exited before reporting readiness"
    assert result.exit_code == 3


@pytest.mark.component
@pytest.mark.small
def test_wait_for_startup_zero_timeout_is_immediate() -> None:
    manager = _child_process(
        _Process(),
        _Connection(),
    )

    result = manager.wait_for_startup(0.0)

    assert not result.ready
    assert result.error == "startup timed out"


@pytest.mark.component
@pytest.mark.small
def test_generation_update_requires_matching_acknowledgement() -> None:
    readiness = _Connection(received=[GenerationApplied(8)])
    control = _Connection()
    manager = _child_process(_Process(), readiness, control)

    manager.set_generation(8, timeout=1.0)

    assert control.sent == [GenerationUpdate(8)]


@pytest.mark.component
@pytest.mark.small
def test_generation_update_rejects_wrong_acknowledgement() -> None:
    manager = _child_process(
        _Process(),
        _Connection(received=[GenerationApplied(7)]),
    )

    with pytest.raises(RuntimeError, match="invalid generation acknowledgement"):
        manager.set_generation(8, timeout=1.0)


@pytest.mark.component
@pytest.mark.small
def test_generation_update_distinguishes_dead_child_timeout() -> None:
    manager = _child_process(
        _Process(alive=False),
        _Connection(polls=[False]),
    )

    with pytest.raises(RuntimeError, match="exited before applying generation update"):
        manager.set_generation(8, timeout=1.0)


@pytest.mark.component
@pytest.mark.small
def test_stop_escalates_from_shutdown_to_terminate_to_kill() -> None:
    process = _Process(alive=True, exitcode=-9)
    readiness = _Connection()
    control = _Connection()
    manager = _child_process(process, readiness, control)

    exit_code = manager.stop(grace_timeout=0.1, terminate_timeout=0.2)

    assert exit_code == -9
    assert control.sent == [ChildCommand.SHUTDOWN]
    assert process.terminate_called
    assert process.kill_called
    assert process.join_timeouts == [0.1, 0.2, 0.2]
    assert process.closed
    assert readiness.closed
    assert control.closed

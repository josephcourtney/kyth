from __future__ import annotations

import importlib
import inspect
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, cast

from kyth.model import DataDependency, RenderRecord, SourceVersion

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterator

_INSTALL_LOCK = Lock()


@dataclass(slots=True)
class RenderTrace:
    """Request-scoped Jinja dependency capture."""

    render_id: str
    generation: int
    dependencies: dict[str, SourceVersion] = field(default_factory=dict)
    adapters: set[str] = field(default_factory=set)
    data_dependencies: dict[tuple[str, str], DataDependency] = field(default_factory=dict)
    complete: bool = True
    used: bool = False

    def record_template(self, template: object) -> None:
        """Record one concrete template object used by the current render."""
        self.used = True
        self.adapters.add("jinja")
        try:
            filename = object.__getattribute__(template, "filename")  # ruff: ignore[unnecessary-dunder-call]
        except AttributeError:
            self.complete = False
            return
        if not isinstance(filename, str) or not filename or filename.startswith("<"):
            self.complete = False
            return
        self.record_path(filename, adapter="jinja")

    def record_path(self, path: str | Path, *, adapter: str) -> None:
        """Record one explicit filesystem dependency using the normal source-version model."""
        self.used = True
        self.adapters.add(adapter)
        version, complete = _source_version(path)
        if not complete:
            self.complete = False
        self.dependencies[version.path] = version

    def record_data(self, identity: str, path: str | Path) -> None:
        """Record one semantic browser-data dependency."""
        self.used = True
        self.adapters.add("data")
        version, complete = _source_version(path)
        if not complete:
            self.complete = False
        self.data_dependencies[(identity, version.path)] = DataDependency(identity, version)

    def to_record(self) -> RenderRecord:
        """Freeze this request trace into the adapter-neutral provenance model."""
        adapter = "+".join(sorted(self.adapters)) or "unknown"
        return RenderRecord(
            render_id=self.render_id,
            generation=self.generation,
            dependencies=tuple(sorted(self.dependencies.values(), key=lambda item: item.path)),
            complete=self.complete,
            adapter=adapter,
            data_dependencies=tuple(
                sorted(self.data_dependencies.values(), key=lambda item: (item.identity, item.source.path))
            ),
        )


_CURRENT_TRACE: ContextVar[RenderTrace | None] = ContextVar("kyth_jinja_render_trace", default=None)


@contextmanager
def capture_render(render_id: str, generation: int) -> Iterator[RenderTrace]:
    """Capture Jinja templates used while one ASGI request renders."""
    trace = RenderTrace(render_id, generation)
    token = _CURRENT_TRACE.set(trace)
    try:
        yield trace
    finally:
        _CURRENT_TRACE.reset(token)


def record_dependency(path: str | Path) -> bool:
    """Attach one explicit source dependency to the active request render, if any."""
    trace = _CURRENT_TRACE.get()
    if trace is None:
        return False
    trace.record_path(path, adapter="explicit")
    return True


def record_data_dependency(identity: str, path: str | Path) -> bool:
    """Attach semantic data provenance to the active request render, if any."""
    trace = _CURRENT_TRACE.get()
    if trace is None:
        return False
    trace.record_data(identity, path)
    return True


def install_jinja_tracing() -> bool:
    """Install zero-touch Jinja tracing when Jinja is available in the child."""
    try:
        module = importlib.import_module("jinja2.environment")
    except ModuleNotFoundError as exc:
        if exc.name in {"jinja2", "jinja2.environment"}:
            return False
        raise

    environment_class = vars(module).get("Environment")
    template_class = vars(module).get("Template")
    if not isinstance(environment_class, type) or not isinstance(template_class, type):
        return False

    with _INSTALL_LOCK:
        if bool(vars(environment_class).get("_kyth_tracing_installed", False)):
            return True
        _patch_environment(environment_class)
        _patch_template(template_class)
        _set_attribute(environment_class, "_kyth_tracing_installed", value=True)
    return True


def _patch_environment(environment_class: type[object]) -> None:
    original_get_template = cast(
        "Callable[..., object]",
        vars(environment_class)["get_template"],
    )
    original_select_template = cast(
        "Callable[..., object]",
        vars(environment_class)["select_template"],
    )

    def get_template(environment: object, *args: object, **kwargs: object) -> object:
        template = original_get_template(environment, *args, **kwargs)
        _record_template(template)
        return template

    def select_template(environment: object, *args: object, **kwargs: object) -> object:
        template = original_select_template(environment, *args, **kwargs)
        _record_template(template)
        return template

    _set_attribute(environment_class, "get_template", get_template)
    _set_attribute(environment_class, "select_template", select_template)


def _patch_template(template_class: type[object]) -> None:
    original_render = cast("Callable[..., object]", vars(template_class)["render"])
    original_render_async = cast(
        "Callable[..., object]",
        vars(template_class)["render_async"],
    )

    def render(template: object, *args: object, **kwargs: object) -> object:
        _record_template(template)
        return original_render(template, *args, **kwargs)

    async def render_async(template: object, *args: object, **kwargs: object) -> object:
        _record_template(template)
        result = original_render_async(template, *args, **kwargs)
        if not inspect.isawaitable(result):
            return result
        return await cast("Awaitable[object]", result)

    _set_attribute(template_class, "render", render)
    _set_attribute(template_class, "render_async", render_async)


def _record_template(template: object) -> None:
    trace = _CURRENT_TRACE.get()
    if trace is not None:
        trace.record_template(template)


def _set_attribute(target: object, name: str, value: object) -> None:
    setattr(target, name, value)


def _source_version(path: str | Path) -> tuple[SourceVersion, bool]:
    resolved = Path(path).expanduser().resolve(strict=False)
    try:
        stat = resolved.stat()
    except OSError:
        return SourceVersion(str(resolved), None, None), False
    return SourceVersion(str(resolved), stat.st_mtime_ns, stat.st_size), True

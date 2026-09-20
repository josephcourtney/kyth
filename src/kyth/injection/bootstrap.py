from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING

from kyth.injection.html import browser_script

if TYPE_CHECKING:
    from collections.abc import Iterator


@dataclass(slots=True)
class ClientBootstrap:
    """Request-local metadata shared by automatic and explicit client inclusion."""

    control_url: str
    token: str
    generation: int
    render_id: str
    nonce: str
    explicit_included: bool = False
    headers_committed: bool = False

    def explicit_script(self) -> str:
        """Render the client once while response headers can still be adjusted."""
        if self.headers_committed:
            msg = "Kyth client_script() must be called before response headers are committed"
            raise RuntimeError(msg)
        if self.explicit_included:
            msg = "Kyth client_script() may only be included once per response"
            raise RuntimeError(msg)
        self.explicit_included = True
        return browser_script(
            control_url=self.control_url,
            token=self.token,
            generation=self.generation,
            render_id=self.render_id,
            nonce=self.nonce,
        ).decode()


_CURRENT_BOOTSTRAP: ContextVar[ClientBootstrap | None] = ContextVar(
    "kyth_client_bootstrap",
    default=None,
)


@contextmanager
def capture_client_bootstrap(bootstrap: ClientBootstrap) -> Iterator[ClientBootstrap]:
    """Expose one bootstrap only to code running in the current request context."""
    token = _CURRENT_BOOTSTRAP.set(bootstrap)
    try:
        yield bootstrap
    finally:
        _CURRENT_BOOTSTRAP.reset(token)


def client_script() -> str:
    """Return the explicit Kyth client tag for the current managed request.

    Outside a Kyth-managed HTTP request this returns an empty string so optional
    development integration does not alter normal application output.
    """
    bootstrap = _CURRENT_BOOTSTRAP.get()
    if bootstrap is None:
        return ""
    return bootstrap.explicit_script()

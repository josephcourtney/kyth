from __future__ import annotations

import socket
import sys
from typing import Protocol

if sys.platform == "win32":
    from multiprocessing.resource_sharer import DupSocket
else:
    from multiprocessing.resource_sharer import DupFd

DEFAULT_BACKLOG = 2048


class SocketTransfer(Protocol):
    """Picklable transfer object that can yield a duplicated socket resource."""

    def detach(self) -> int | socket.socket:
        """Detach the duplicated descriptor or socket exactly once."""
        ...


def bind_listening_socket(host: str, port: int, *, backlog: int = DEFAULT_BACKLOG) -> socket.socket:
    """Bind the public application socket once for the supervisor lifetime."""
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM, flags=socket.AI_PASSIVE)
    if not infos:
        msg = f"could not resolve listening address {host!r}:{port}"
        raise OSError(msg)

    errors: list[OSError] = []
    for family, socktype, proto, _, sockaddr in infos:
        sock = socket.socket(family, socktype, proto)
        try:
            if family in {socket.AF_INET, socket.AF_INET6}:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(sockaddr)
            sock.listen(backlog)
        except OSError as exc:
            errors.append(exc)
            sock.close()
            continue
        return sock

    if errors:
        raise errors[-1]
    msg = f"could not bind listening address {host!r}:{port}"
    raise OSError(msg)


def duplicate_listening_socket(sock: socket.socket) -> tuple[SocketTransfer, int, int, int]:
    """Create a picklable transfer that does not serialize the socket object itself."""
    transfer: SocketTransfer
    if sys.platform == "win32":
        transfer = DupSocket(sock)
    else:
        transfer = DupFd(sock.fileno())

    return transfer, int(sock.family), int(sock.type), sock.proto


def rebuild_listening_socket(
    transfer: SocketTransfer,
    family: int,
    socktype: int,
    proto: int,
) -> socket.socket:
    """Rebuild the child-owned duplicate of the supervisor listening socket."""
    resource = transfer.detach()
    if isinstance(resource, socket.socket):
        return resource
    return socket.socket(family, socktype, proto, fileno=resource)

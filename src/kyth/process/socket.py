from __future__ import annotations

import socket

DEFAULT_BACKLOG = 2048


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

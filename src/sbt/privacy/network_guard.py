"""Offline-mode enforcement: refuse every outbound connection that is not to this computer.

Installed once at start-up in offline mode. It is a second line of defence behind the rule that only
`is_local` engines can be constructed — if any code path (including a third-party library) tries to reach
the network, the job fails loudly instead of leaking document content.
"""
from __future__ import annotations

import ipaddress
import socket

_installed = False


class OfflineViolation(RuntimeError):
    pass


def _is_loopback(address: object) -> bool:
    if isinstance(address, (tuple, list)) and address:
        host = str(address[0])
    else:
        return True          # AF_UNIX paths etc. are local
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False         # unresolved hostnames are not allowed


def install() -> None:
    global _installed
    if _installed:
        return
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def connect(self: socket.socket, address: object) -> None:
        if not _is_loopback(address):
            raise OfflineViolation("Offline mode: blocked a non-local network connection")
        return original_connect(self, address)

    def connect_ex(self: socket.socket, address: object) -> int:
        if not _is_loopback(address):
            raise OfflineViolation("Offline mode: blocked a non-local network connection")
        return original_connect_ex(self, address)

    socket.socket.connect = connect          # type: ignore[method-assign]
    socket.socket.connect_ex = connect_ex    # type: ignore[method-assign]
    _installed = True

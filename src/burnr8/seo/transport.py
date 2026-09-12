"""Connect crawler requests only to validated public addresses, preserving TLS hosts."""

from __future__ import annotations

import ipaddress
import socket
from typing import Any

from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import NewConnectionError
from urllib3.util.connection import create_connection


def public_addresses(host: str, port: int) -> list[str]:
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise ValueError(f"Could not resolve crawler host {host}.") from error
    if not addresses:
        raise ValueError(f"Could not resolve crawler host {host}.")
    result = []
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global or ip.is_multicast:
            raise ValueError(f"Crawler rejected non-public address for {host}.")
        result.append(str(ip))
    return list(dict.fromkeys(result))


def _connect_public(connection: HTTPConnection) -> socket.socket:
    # Resolve at connection time, then pass a numeric IP to the socket helper.
    # The connection's original host remains intact for Host, SNI and TLS checks.
    addresses = public_addresses(connection.host, connection.port)
    last_error: OSError | None = None
    for address in addresses:
        try:
            return create_connection(
                (address, connection.port),
                connection.timeout,
                source_address=connection.source_address,
                socket_options=connection.socket_options,
            )
        except OSError as error:
            last_error = error
    raise NewConnectionError(connection, "Could not connect to a public crawler address.") from last_error


class _PublicHTTPConnection(HTTPConnection):
    def _new_conn(self) -> socket.socket:
        return _connect_public(self)


class _PublicHTTPSConnection(HTTPSConnection):
    def _new_conn(self) -> socket.socket:
        return _connect_public(self)


class _PublicHTTPPool(HTTPConnectionPool):
    ConnectionCls = _PublicHTTPConnection


class _PublicHTTPSPool(HTTPSConnectionPool):
    ConnectionCls = _PublicHTTPSConnection


class PublicAddressAdapter(HTTPAdapter):
    def init_poolmanager(self, connections: int, maxsize: int, block: bool = False, **pool_kwargs: Any) -> None:
        super().init_poolmanager(connections, maxsize, block, **pool_kwargs)  # type: ignore[no-untyped-call]
        # Assign a private mapping; do not alter urllib3's process-global defaults.
        self.poolmanager.pool_classes_by_scheme = {"http": _PublicHTTPPool, "https": _PublicHTTPSPool}

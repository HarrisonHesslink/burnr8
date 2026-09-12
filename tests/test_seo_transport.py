"""The crawler must enforce public destinations when opening the actual socket."""

from unittest.mock import MagicMock, patch

import pytest
from urllib3.connection import HTTPSConnection
from urllib3.poolmanager import PoolManager

from burnr8.seo.crawler import SafeWebFetcher
from burnr8.seo.transport import _connect_public


@pytest.mark.parametrize("destination", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "224.0.0.1"])
def test_dns_change_to_private_address_is_rejected_before_connection(destination):
    public = [(2, 1, 6, "", ("93.184.216.34", 80))]
    private = [(2, 1, 6, "", (destination, 80))]
    with (
        patch("burnr8.seo.transport.socket.getaddrinfo", side_effect=[public, private]) as resolve,
        patch("burnr8.seo.transport.create_connection") as connect,
        pytest.raises(ValueError, match="non-public"),
    ):
        SafeWebFetcher().fetch("http://example.test/")
    assert resolve.call_count == 2
    connect.assert_not_called()


def test_socket_uses_resolved_public_ip_while_tls_host_remains_original():
    connection = HTTPSConnection("example.test", port=443, timeout=2)
    public = [(2, 1, 6, "", ("93.184.216.34", 443))]
    sock = MagicMock()
    with (
        patch("burnr8.seo.transport.socket.getaddrinfo", return_value=public) as resolve,
        patch("burnr8.seo.transport.create_connection", return_value=sock) as connect,
    ):
        assert _connect_public(connection) is sock
    assert connect.call_args.args == (("93.184.216.34", 443), 2)
    assert connection.host == "example.test"
    assert resolve.call_count == 1


def test_crawler_does_not_change_other_clients_connection_pools():
    previous = dict(PoolManager().pool_classes_by_scheme)
    fetcher = SafeWebFetcher()
    assert PoolManager().pool_classes_by_scheme == previous
    for scheme in ("http", "https"):
        adapter = fetcher.session.get_adapter(scheme + "://example.test")
        assert adapter.poolmanager.pool_classes_by_scheme[scheme] is not previous[scheme]

"""Protocol used to talk to dserver.

Every request carries the user's token, so dserver is contacted over https
by default. Plain http is the default only for loopback hosts, such as a
local development server. A per-server DSERVER_PROTOCOL_<host[:port]>, as
stored by `dtool dserver login http://...`, overrides DSERVER_PROTOCOL, which
overrides the default.
"""

import json


import pytest
import requests

from dtool_dserver.storagebroker import (
    DServerStorageBroker,
    DServerStorageBrokerError,
)

UUID = "550e8400-e29b-41d4-a716-446655440000"


def _broker(server):
    return DServerStorageBroker(f"dserver://{server}/s3/bucket/{UUID}")


@pytest.fixture(autouse=True)
def no_protocol_config(monkeypatch, tmp_path):
    import os
    for key in list(os.environ):
        if key.startswith("DSERVER_PROTOCOL"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("DSERVER_TOKEN", "token")
    # Do not pick up the user's dtool configuration.
    monkeypatch.setattr("dtoolcore.utils.DEFAULT_CONFIG_PATH",
                        str(tmp_path / "dtool.json"))


@pytest.mark.parametrize("server", [
    "dserver.example.org",
    "dserver.example.org:5000",
    "192.168.1.10:5000",
    "localhost.example.org",
])
def test_https_by_default(server):
    assert _broker(server)._get_server_url("/x") == f"https://{server}/x"


@pytest.mark.parametrize("server", [
    "localhost",
    "localhost:5000",
    "127.0.0.1:5000",
    "127.1.2.3",
    "[::1]:5000",
])
def test_http_by_default_for_loopback(server):
    assert _broker(server)._get_server_url("/x") == f"http://{server}/x"


def test_explicit_http_for_remote_server(monkeypatch):
    monkeypatch.setenv("DSERVER_PROTOCOL", "http")
    url = _broker("dserver.example.org")._get_server_url("/x")
    assert url == "http://dserver.example.org/x"


def test_explicit_https_for_localhost(monkeypatch):
    monkeypatch.setenv("DSERVER_PROTOCOL", "https")
    assert _broker("localhost:5000")._get_server_url("/x") == \
        "https://localhost:5000/x"


def test_invalid_protocol_rejected(monkeypatch):
    monkeypatch.setenv("DSERVER_PROTOCOL", "ftp")
    with pytest.raises(DServerStorageBrokerError, match="DSERVER_PROTOCOL"):
        _broker("dserver.example.org")._get_server_url("/x")


def _write_config(tmp_path, **values):
    with open(tmp_path / "dtool.json", "w") as fh:
        json.dump(values, fh)


def test_per_server_protocol(tmp_path):
    _write_config(tmp_path, **{"DSERVER_PROTOCOL_lan-server:5000": "http"})
    assert _broker("lan-server:5000")._get_server_url("/x") == \
        "http://lan-server:5000/x"
    # Other servers keep the default.
    assert _broker("lan-server:5001")._get_server_url("/x") == \
        "https://lan-server:5001/x"
    assert _broker("dserver.example.org")._get_server_url("/x") == \
        "https://dserver.example.org/x"


def test_per_server_protocol_overrides_global(monkeypatch, tmp_path):
    monkeypatch.setenv("DSERVER_PROTOCOL", "https")
    _write_config(tmp_path, **{"DSERVER_PROTOCOL_lan-server": "http"})
    assert _broker("lan-server")._get_server_url("/x") == \
        "http://lan-server/x"


def test_invalid_per_server_protocol_rejected(tmp_path):
    _write_config(tmp_path, **{"DSERVER_PROTOCOL_lan-server": "ftp"})
    with pytest.raises(DServerStorageBrokerError,
                       match="DSERVER_PROTOCOL_lan-server"):
        _broker("lan-server")._get_server_url("/x")


def test_listing_uses_same_default(monkeypatch):
    requested = []

    class Response:
        headers = {}

        def raise_for_status(self):
            pass

        def json(self):
            return []

    def fake_post(url, **kwargs):
        requested.append(url)
        return Response()

    monkeypatch.setattr(requests, "post", fake_post)

    DServerStorageBroker.list_dataset_uris(
        "dserver://dserver.example.org/s3/bucket")
    DServerStorageBroker.list_dataset_uris("dserver://localhost:5000/s3/bucket")

    assert requested == [
        "https://dserver.example.org/uris",
        "http://localhost:5000/uris",
    ]


def test_https_connection_error_hints_at_protocol(monkeypatch):
    """A dserver that only speaks http fails with an https connection error;
    point users at logging in over http."""
    def refuse(*args, **kwargs):
        raise requests.exceptions.SSLError("wrong version number")

    monkeypatch.setattr(requests, "request", refuse)

    with pytest.raises(DServerStorageBrokerError,
                       match="dtool dserver login http://dserver.example.org"):
        _broker("dserver.example.org")._api_request("GET", "/x")


def test_cache_dir_from_config_file(tmp_path):
    """DSERVER_CACHE_DIR is read like every other setting: environment or
    dtool config file."""
    _write_config(tmp_path, DSERVER_CACHE_DIR=str(tmp_path / "cache"))
    assert _broker("dserver.example.org")._get_cache_dir() == \
        str(tmp_path / "cache" / UUID)


def test_cache_dir_from_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("DSERVER_CACHE_DIR", str(tmp_path / "env-cache"))
    _write_config(tmp_path, DSERVER_CACHE_DIR=str(tmp_path / "cache"))
    assert _broker("dserver.example.org")._get_cache_dir() == \
        str(tmp_path / "env-cache" / UUID)

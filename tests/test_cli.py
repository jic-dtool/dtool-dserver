"""`dtool dserver login | logout | status` commands."""

import json

import pytest
from click.testing import CliRunner

from dtool_dserver import auth
from dtool_dserver.cli import dserver

from .test_auth import (  # NOQA
    DEVICE,
    SERVER,
    FakeResponse,
    FakeServer,
    config_path,
    make_token,
)

PROTOCOL_KEY = f"DSERVER_PROTOCOL_{SERVER}"


@pytest.fixture
def server(monkeypatch):
    fake = FakeServer(monkeypatch)
    fake.route("GET", "/me", lambda kwargs: FakeResponse(200, {
        "username": auth.token_claims(
            kwargs["headers"]["Authorization"][len("Bearer "):])["sub"],
        "is_admin": False,
    }))
    monkeypatch.setattr(auth.time, "sleep", lambda s: None)
    return fake


def _invoke(*args, input=None):
    return CliRunner().invoke(dserver, list(args), input=input)


def test_login_with_device_flow(config_path, server):  # NOQA
    token = make_token("alice")
    server.route("GET", "/auth/oauth2/info",
                 FakeResponse(200, {"provider": "orcid", "configured": True}))
    server.route("POST", "/auth/oauth2/device", FakeResponse(200, DEVICE))
    server.route("POST", "/auth/oauth2/device/token",
                 FakeResponse(200, {"token": token}))

    result = _invoke("login", SERVER, "--no-browser")

    assert result.exit_code == 0, result.output
    assert DEVICE["verification_uri_complete"] in result.output
    assert "WDJB-MJHT" in result.output
    assert f"Logged in to {SERVER} as alice" in result.output
    with open(config_path) as fh:
        assert json.load(fh)[auth.token_key(SERVER)] == token


def test_login_with_ldap(config_path, server):  # NOQA
    token = make_token("bob")
    server.route("GET", "/auth/ldap/info", FakeResponse(200, {}))
    server.route("POST", "/auth/ldap/token",
                 FakeResponse(200, {"token": token}))

    result = _invoke("login", SERVER, "--username", "bob",
                     input="secret\n")

    assert result.exit_code == 0, result.output
    assert "secret" not in result.output
    assert server.calls[-2][2]["json"] == {"username": "bob",
                                           "password": "secret"}
    assert f"Logged in to {SERVER} as bob" in result.output


def test_login_method_option(config_path, server):  # NOQA
    """--method skips discovery, e.g. when both methods are offered."""
    token = make_token("bob")
    server.route("POST", "/auth/ldap/token",
                 FakeResponse(200, {"token": token}))
    result = _invoke("login", SERVER, "--method", "ldap", "--username",
                     "bob", input="secret\n")
    assert result.exit_code == 0, result.output
    assert not any(path.endswith("/info") for _, path, _ in server.calls)


def test_login_without_methods_fails(config_path, server):  # NOQA
    result = _invoke("login", SERVER)
    assert result.exit_code != 0
    assert "No login method" in result.output


def test_login_rejected_token_not_stored(config_path, server):  # NOQA
    """A token for a user that is not registered in dserver is useless."""
    server.route("GET", "/auth/ldap/info", FakeResponse(200, {}))
    server.route("POST", "/auth/ldap/token",
                 FakeResponse(200, {"token": make_token("mallory")}))
    server.route("GET", "/me", FakeResponse(401, {"msg": "unknown user"}))

    result = _invoke("login", SERVER, "--username", "mallory",
                     input="secret\n")

    assert result.exit_code != 0
    assert auth.stored_servers(config_path=config_path) == []


def test_logout(config_path, server):  # NOQA
    auth.store_token(SERVER, make_token(), config_path=config_path)
    result = _invoke("logout", SERVER)
    assert result.exit_code == 0, result.output
    assert auth.stored_servers(config_path=config_path) == []
    result = _invoke("logout", SERVER)
    assert "Not logged in" in result.output


def test_status(config_path, server):  # NOQA
    auth.store_token(SERVER, make_token("alice", expires_in=7200),
                     config_path=config_path)
    auth.store_token("old.example.org", make_token("carol", expires_in=-60),
                     config_path=config_path)

    result = _invoke("status")

    assert result.exit_code == 0, result.output
    assert SERVER in result.output and "alice" in result.output
    assert "old.example.org" in result.output and "expired" in result.output


def test_status_without_logins(config_path, server):  # NOQA
    result = _invoke("status")
    assert result.exit_code == 0
    assert "Not logged in" in result.output



def _ldap_routes(server, token):
    server.route("POST", "/auth/ldap/token",
                 FakeResponse(200, {"token": token}))
    server.route("GET", "/me", lambda kwargs: FakeResponse(
        200, {"username": "bob"}))


def _config(config_path):  # NOQA
    with open(config_path) as fh:
        return json.load(fh)


def test_login_over_http_remembers_protocol(config_path, monkeypatch):  # NOQA
    """`dtool dserver login http://host` talks http to this server, now and
    later, without any configuration."""
    server = FakeServer(monkeypatch, url=f"http://{SERVER}")
    _ldap_routes(server, make_token("bob"))

    result = _invoke("login", f"http://{SERVER}", "--method", "ldap",
                     "--username", "bob", input="secret\n")

    assert result.exit_code == 0, result.output
    assert "unencrypted" in result.output
    assert _config(config_path)[PROTOCOL_KEY] == "http"

    from dtool_dserver.connection import server_url
    assert server_url(SERVER) == f"http://{SERVER}"
    assert f"{SERVER} (http)" in _invoke("status").output


def test_login_over_https_forgets_http(config_path, monkeypatch):  # NOQA
    with open(config_path, "w") as fh:
        json.dump({PROTOCOL_KEY: "http"}, fh)
    server = FakeServer(monkeypatch)  # https
    _ldap_routes(server, make_token("bob"))

    result = _invoke("login", f"https://{SERVER}", "--method", "ldap",
                     "--username", "bob", input="secret\n")

    assert result.exit_code == 0, result.output
    assert "unencrypted" not in result.output
    assert PROTOCOL_KEY not in _config(config_path)


def test_login_without_scheme_keeps_protocol(config_path, monkeypatch):  # NOQA
    with open(config_path, "w") as fh:
        json.dump({PROTOCOL_KEY: "http"}, fh)
    server = FakeServer(monkeypatch, url=f"http://{SERVER}")
    _ldap_routes(server, make_token("bob"))

    result = _invoke("login", SERVER, "--method", "ldap",
                     "--username", "bob", input="secret\n")

    assert result.exit_code == 0, result.output
    assert _config(config_path)[PROTOCOL_KEY] == "http"


def test_failed_login_does_not_store_protocol(config_path, monkeypatch):  # NOQA
    server = FakeServer(monkeypatch, url=f"http://{SERVER}")
    server.route("POST", "/auth/ldap/token",
                 FakeResponse(401, {"error": "Invalid credentials"}))

    result = _invoke("login", f"http://{SERVER}", "--method", "ldap",
                     "--username", "bob", input="wrong\n")

    assert result.exit_code != 0
    import os
    assert not os.path.exists(config_path) or \
        PROTOCOL_KEY not in _config(config_path)


def test_logout_forgets_protocol(config_path, monkeypatch):  # NOQA
    with open(config_path, "w") as fh:
        json.dump({PROTOCOL_KEY: "http",
                   auth.token_key(SERVER): make_token("bob")}, fh)
    result = _invoke("logout", SERVER)
    assert result.exit_code == 0, result.output
    assert _config(config_path) == {}

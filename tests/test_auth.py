"""Token lookup, storage, automatic refresh and login flows."""

import base64
import json
import os
import stat
import time

import pytest
import requests

from dtool_dserver import auth
from dtool_dserver.errors import DServerAuthenticationError

SERVER = "dserver.example.org"
URL = f"https://{SERVER}"


def make_token(sub="alice", expires_in=3600, **claims):
    """Return an (unsigned) JWT with the given claims."""
    def b64(data):
        return base64.urlsafe_b64encode(
            json.dumps(data).encode()).rstrip(b"=").decode()
    now = int(time.time())
    payload = {"sub": sub, "username": sub, "iat": now,
               "exp": now + expires_in}
    payload.update(claims)
    return f"{b64({'alg': 'RS256', 'typ': 'JWT'})}.{b64(payload)}.sig"


class FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.text = json.dumps(self._json)

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(
                f"{self.status_code}", response=self)


class FakeServer:
    """Routes requests.request calls to handlers by (method, path)."""

    def __init__(self, monkeypatch, url=URL):
        self.url = url
        self.routes = {}
        self.calls = []
        # Every dserver answers its health check without authentication.
        self.route("GET", "/config/health",
                   FakeResponse(200, {"status": "healthy"}))
        monkeypatch.setattr(requests, "request", self.request)

    def route(self, method, path, *responses):
        self.routes[(method, path)] = list(responses)

    def request(self, method, url, **kwargs):
        assert url.startswith(self.url), url
        path = url[len(self.url):]
        self.calls.append((method, path, kwargs))
        responses = self.routes.get((method, path))
        if not responses:
            return FakeResponse(404, {"error": "not found"})
        response = responses[0] if len(responses) == 1 else responses.pop(0)
        return response(kwargs) if callable(response) else response


@pytest.fixture
def config_path(tmp_path, monkeypatch):
    for key in list(os.environ):
        if key.startswith("DSERVER_"):
            monkeypatch.delenv(key)
    path = tmp_path / "dtool.json"
    monkeypatch.setattr("dtoolcore.utils.DEFAULT_CONFIG_PATH", str(path))
    return str(path)


@pytest.fixture
def server(monkeypatch):
    return FakeServer(monkeypatch)


def _read(config_path):
    with open(config_path) as fh:
        return json.load(fh)


# --- lookup and storage -----------------------------------------------------

def test_token_key_per_server():
    assert auth.token_key("dserver.example.org:5000") == \
        "DSERVER_TOKEN_dserver.example.org:5000"


def test_stored_token_used(config_path):
    token = make_token()
    auth.store_token(SERVER, token, config_path=config_path)
    assert auth.lookup_token(SERVER, config_path=config_path) == token


def test_token_per_server(config_path):
    auth.store_token("a.example.org", make_token("a"),
                     config_path=config_path)
    auth.store_token("b.example.org", make_token("b"),
                     config_path=config_path)
    assert auth.token_claims(auth.lookup_token(
        "b.example.org", config_path=config_path))["sub"] == "b"


def test_per_server_token_takes_precedence_over_global(config_path,
                                                       monkeypatch):
    monkeypatch.setenv("DSERVER_TOKEN", "global-token")
    token = make_token()
    auth.store_token(SERVER, token, config_path=config_path)
    assert auth.lookup_token(SERVER, config_path=config_path) == token
    assert auth.lookup_token("other.example.org",
                             config_path=config_path) == "global-token"


def test_token_file_fallback(config_path, monkeypatch, tmp_path):
    token_file = tmp_path / "token"
    token_file.write_text("file-token\n")
    monkeypatch.setenv("DSERVER_TOKEN_FILE", str(token_file))
    assert auth.lookup_token(SERVER, config_path=config_path) == "file-token"


def test_missing_token_suggests_login(config_path):
    with pytest.raises(DServerAuthenticationError,
                       match=f"dtool dserver login {SERVER}"):
        auth.lookup_token(SERVER, config_path=config_path)


def test_stored_token_file_is_private(config_path):
    auth.store_token(SERVER, make_token(), config_path=config_path)
    assert stat.S_IMODE(os.stat(config_path).st_mode) == 0o600


def test_remove_token(config_path):
    auth.store_token(SERVER, make_token(), config_path=config_path)
    auth.store_token("other.example.org", make_token(),
                     config_path=config_path)
    assert auth.remove_token(SERVER, config_path=config_path) is True
    assert auth.remove_token(SERVER, config_path=config_path) is False
    assert auth.stored_servers(config_path=config_path) == \
        ["other.example.org"]
    assert stat.S_IMODE(os.stat(config_path).st_mode) == 0o600


def test_remove_token_keeps_other_settings(config_path):
    with open(config_path, "w") as fh:
        json.dump({"DTOOL_USER_FULL_NAME": "Alice"}, fh)
    auth.store_token(SERVER, make_token(), config_path=config_path)
    auth.remove_token(SERVER, config_path=config_path)
    assert _read(config_path) == {"DTOOL_USER_FULL_NAME": "Alice"}


# --- automatic refresh -------------------------------------------------------

def test_expiring_stored_token_refreshed(config_path, server):
    old = make_token(expires_in=3600)
    new = make_token(expires_in=24 * 3600)
    auth.store_token(SERVER, old, config_path=config_path)
    server.route("POST", "/auth/oauth2/refresh",
                 FakeResponse(200, {"token": new}))

    assert auth.lookup_token(SERVER, config_path=config_path) == new
    assert _read(config_path)[auth.token_key(SERVER)] == new
    method, path, kwargs = server.calls[0]
    assert kwargs["json"] == {"token": old}


def test_fresh_token_not_refreshed(config_path, server):
    token = make_token(expires_in=20 * 3600)
    auth.store_token(SERVER, token, config_path=config_path)
    assert auth.lookup_token(SERVER, config_path=config_path) == token
    assert server.calls == []


def test_failed_refresh_keeps_token(config_path, server):
    """E.g. an LDAP deployment without refresh, or a session that has
    reached its maximum age."""
    token = make_token(expires_in=3600)
    auth.store_token(SERVER, token, config_path=config_path)
    server.route("POST", "/auth/oauth2/refresh",
                 FakeResponse(401, {"error": "Invalid or expired token"}))
    assert auth.lookup_token(SERVER, config_path=config_path) == token


def test_unreachable_server_keeps_token(config_path, monkeypatch):
    token = make_token(expires_in=3600)
    auth.store_token(SERVER, token, config_path=config_path)

    def refuse(*args, **kwargs):
        raise requests.exceptions.ConnectionError("down")

    monkeypatch.setattr(requests, "request", refuse)
    assert auth.lookup_token(SERVER, config_path=config_path) == token


def test_expired_token_not_refreshed(config_path, server):
    token = make_token(expires_in=-60)
    auth.store_token(SERVER, token, config_path=config_path)
    assert auth.lookup_token(SERVER, config_path=config_path) == token
    assert server.calls == []


def test_tokens_from_environment_never_refreshed(config_path, server,
                                                 monkeypatch):
    token = make_token(expires_in=3600)
    monkeypatch.setenv("DSERVER_TOKEN", token)
    monkeypatch.setenv(auth.token_key("other.example.org"), token)
    assert auth.lookup_token(SERVER, config_path=config_path) == token
    assert auth.lookup_token("other.example.org",
                             config_path=config_path) == token
    assert server.calls == []


# --- login flows -------------------------------------------------------------

def test_available_methods(server):
    server.route("GET", "/auth/oauth2/info",
                 FakeResponse(200, {"provider": "orcid", "configured": True}))
    server.route("GET", "/auth/ldap/info", FakeResponse(404))
    assert auth.available_methods(URL) == ["oauth2"]


def test_available_methods_ldap(server):
    server.route("GET", "/auth/ldap/info", FakeResponse(200, {}))
    assert auth.available_methods(URL) == ["ldap"]


def test_unconfigured_oauth2_not_available(server):
    server.route("GET", "/auth/oauth2/info",
                 FakeResponse(200, {"configured": False}))
    assert auth.available_methods(URL) == []


DEVICE = {
    "device_code": "secret-device-code",
    "user_code": "WDJB-MJHT",
    "verification_uri": "https://webapp.example.org",
    "verification_uri_complete":
        "https://webapp.example.org?user_code=WDJB-MJHT",
    "expires_in": 600,
    "interval": 5,
}


def _pending(error="authorization_pending"):
    return FakeResponse(400, {"error": error})


def test_device_login(server, monkeypatch):
    token = make_token()
    sleeps, shown, opened = [], [], []
    monkeypatch.setattr(auth.time, "sleep", sleeps.append)
    server.route("POST", "/auth/oauth2/device", FakeResponse(200, DEVICE))
    server.route("POST", "/auth/oauth2/device/token",
                 _pending(), _pending("slow_down"),
                 FakeResponse(200, {"token": token}))

    result = auth.device_login(
        URL, client_name="dtool on laptop",
        notify=lambda uri, code: shown.append((uri, code)),
        open_browser=opened.append)

    assert result == token
    assert shown == [(DEVICE["verification_uri_complete"], "WDJB-MJHT")]
    assert opened == [DEVICE["verification_uri_complete"]]
    # interval, interval, interval increased by slow_down
    assert sleeps == [5, 5, 10]
    start = server.calls[0]
    assert start[2]["json"] == {"client_name": "dtool on laptop"}
    poll = server.calls[1]
    assert poll[2]["json"] == {
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "device_code": "secret-device-code",
    }


@pytest.mark.parametrize("error", ["access_denied", "expired_token"])
def test_device_login_fails(server, monkeypatch, error):
    monkeypatch.setattr(auth.time, "sleep", lambda s: None)
    server.route("POST", "/auth/oauth2/device", FakeResponse(200, DEVICE))
    server.route("POST", "/auth/oauth2/device/token", _pending(error))
    with pytest.raises(DServerAuthenticationError):
        auth.device_login(URL, client_name="x",
                          notify=lambda uri, code: None, open_browser=None)


def test_device_login_times_out(server, monkeypatch):
    """Stop polling once the device code has expired locally."""
    clock = [0.0]
    monkeypatch.setattr(auth.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(auth.time, "sleep",
                        lambda s: clock.__setitem__(0, clock[0] + s))
    server.route("POST", "/auth/oauth2/device", FakeResponse(200, DEVICE))
    server.route("POST", "/auth/oauth2/device/token", _pending())
    with pytest.raises(DServerAuthenticationError, match="expired"):
        auth.device_login(URL, client_name="x",
                          notify=lambda uri, code: None, open_browser=None)


def test_ldap_login(server):
    token = make_token()
    server.route("POST", "/auth/ldap/token",
                 FakeResponse(200, {"token": token}))
    assert auth.ldap_login(URL, "alice", "secret") == token
    assert server.calls[0][2]["json"] == {"username": "alice",
                                          "password": "secret"}


def test_ldap_login_wrong_password(server):
    server.route("POST", "/auth/ldap/token",
                 FakeResponse(401, {"error": "Invalid credentials"}))
    with pytest.raises(DServerAuthenticationError,
                       match="Invalid credentials"):
        auth.ldap_login(URL, "alice", "wrong")

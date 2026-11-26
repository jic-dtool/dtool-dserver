"""`dtool dserver login | logout | status` commands."""

import json

import pytest
import requests
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


# --- logging in with the address of the web interface ------------------------

WEBAPP = "dtool.example.org"
API_HOST = "api.example.org"
API = f"https://{API_HOST}/dserver"


class FakePage:
    """A web page, e.g. the index.html of dtool-lookup-webapp."""

    def __init__(self, url, html, status_code=200):
        self.url = url
        self.text = html
        self.status_code = status_code
        self.headers = {"Content-Type": "text/html; charset=utf-8"}

    def json(self):
        raise ValueError("not JSON")


def webapp_html(dserver_url):
    return ('<!DOCTYPE html><html><head><meta charset="utf-8">'
            f'<meta name="dserver-url" content="{dserver_url}">'
            '<title>dtool</title></head><body><div id="app"></div>'
            '</body></html>')


@pytest.fixture
def web(monkeypatch):
    """A web interface at WEBAPP whose dserver API is API.

    Like the Vue development server or nginx with a history fallback, the
    web server answers every path with the page (or 404).
    """
    api = FakeServer(monkeypatch, url=API)
    api.route("GET", "/me", lambda kwargs: FakeResponse(200, {
        "username": auth.token_claims(
            kwargs["headers"]["Authorization"][len("Bearer "):])["sub"]}))
    _ldap_routes(api, make_token("bob"))
    api_request = api.request
    pages = {}

    def request(method, url, **kwargs):
        if url.startswith(API):
            return api_request(method, url, **kwargs)
        for prefix, page in pages.items():
            if url.startswith(prefix):
                return page(url)
        raise requests.exceptions.ConnectionError(f"no server at {url}")

    monkeypatch.setattr(requests, "request", request)
    monkeypatch.setattr(auth.time, "sleep", lambda s: None)
    pages[f"https://{WEBAPP}"] = lambda url: FakePage(url, webapp_html(API))
    return pages


def test_login_with_web_interface_address(config_path, web):  # NOQA
    """The address of the web interface, copied from the browser, works for
    logging in. The token is stored for the dserver (its API is served
    under a path here); dserver:// URIs with the host of either work."""
    result = _invoke("login", f"https://{WEBAPP}/search?q=x#top",
                     "--method", "ldap", "--username", "bob",
                     input="y\nsecret\n")

    assert result.exit_code == 0, result.output
    assert f"web interface of the dserver at {API}" in result.output
    # The dserver is on another host than the web interface: confirm.
    assert "on a different host than the web interface" in result.output
    assert f"Log in to {API}? [y/N]" in result.output
    assert f"Logged in to {API_HOST} as bob" in result.output
    assert f"dtool ls dserver://{WEBAPP}/" in result.output
    config = _config(config_path)
    assert auth.token_claims(
        config[auth.token_key(API_HOST)])["sub"] == "bob"
    assert config[f"DSERVER_URL_{API_HOST}"] == API
    assert config[f"DSERVER_URL_{WEBAPP}"] == API
    assert auth.token_key(WEBAPP) not in config

    from dtool_dserver.connection import server_url
    for name in (WEBAPP, API_HOST):
        assert server_url(name) == API
        assert auth.token_claims(auth.lookup_token(name))["sub"] == "bob"
    assert f"{API_HOST} (dserver at {API}) [also as {WEBAPP}]: bob" in \
        _invoke("status").output

    # Logging out of the web interface logs out of its dserver.
    result = _invoke("logout", WEBAPP)
    assert result.exit_code == 0
    assert f"Logged out of {WEBAPP}" in result.output
    assert _config(config_path) == {}


def test_login_with_web_interface_of_dserver_at_root(config_path,  # NOQA
                                                     monkeypatch):
    """An API at the root of its host needs no stored URL."""
    api = FakeServer(monkeypatch, url="http://localhost:5000")
    _ldap_routes(api, make_token("bob"))
    api_request = api.request

    def request(method, url, **kwargs):
        if url.startswith("http://localhost:8080"):
            return FakePage(url, webapp_html("http://localhost:5000"))
        return api_request(method, url, **kwargs)

    monkeypatch.setattr(requests, "request", request)

    result = _invoke("login", "http://localhost:8080/", "--method", "ldap",
                     "--username", "bob", input="secret\n")

    assert result.exit_code == 0, result.output
    assert "Logged in to localhost:5000 as bob" in result.output
    assert _config(config_path).keys() == {
        auth.token_key("localhost:5000"), "DSERVER_URL_localhost:8080"}
    assert auth.lookup_token("localhost:8080") == \
        auth.lookup_token("localhost:5000")


def test_declined_login_through_web_interface(config_path, web):  # NOQA
    result = _invoke("login", WEBAPP, "--method", "ldap",
                     "--username", "bob", input="n\n")

    assert result.exit_code != 0
    assert "Aborted" in result.output
    assert "Password" not in result.output
    import os
    assert not os.path.exists(config_path)


def test_no_discovery_when_using_uris(config_path, web):  # NOQA
    """Only an explicit login makes a web interface's host stand for its
    dserver. A dserver:// URI naming some host must not make dtool look up
    (and trust) a dserver named by that host's page."""
    token = make_token("bob")
    with open(config_path, "w") as fh:
        json.dump({auth.token_key(API_HOST): token,
                   f"DSERVER_URL_{API_HOST}": API}, fh)

    with pytest.raises(auth.DServerAuthenticationError,
                       match=f"Not logged in to dserver {WEBAPP}"):
        auth.lookup_token(WEBAPP)
    assert f"DSERVER_URL_{WEBAPP}" not in _config(config_path)


def test_login_with_web_interface_host_only(config_path, web):  # NOQA
    result = _invoke("login", WEBAPP, "--method", "ldap", "--yes",
                     "--username", "bob", input="secret\n")
    assert result.exit_code == 0, result.output
    assert "[y/N]" not in result.output
    assert _config(config_path)[f"DSERVER_URL_{API_HOST}"] == API


def test_web_interface_with_relative_dserver_url(config_path, web,  # NOQA
                                                 monkeypatch):
    """The web interface may name its dserver relative to itself, e.g. when
    a reverse proxy serves the API under a path of the same host."""
    web[f"https://{WEBAPP}"] = lambda url: FakePage(
        url, webapp_html("../dserver"))
    monkeypatch.setattr(
        auth, "is_dserver", lambda url: url == f"https://{WEBAPP}/dserver")

    assert auth.find_dserver(f"https://{WEBAPP}/app/") == \
        f"https://{WEBAPP}/dserver"


def test_login_to_dserver_api_stores_no_url(config_path, monkeypatch):  # NOQA
    """Logging in to the dserver API itself needs no mapping."""
    server = FakeServer(monkeypatch)
    _ldap_routes(server, make_token("bob"))
    with open(config_path, "w") as fh:
        json.dump({f"DSERVER_URL_{SERVER}": "https://stale.example.org"}, fh)

    result = _invoke("login", SERVER, "--method", "ldap",
                     "--username", "bob", input="secret\n")

    assert result.exit_code == 0, result.output
    assert "web interface" not in result.output
    assert f"DSERVER_URL_{SERVER}" not in _config(config_path)


def test_login_to_web_page_without_dserver_fails(config_path, web):  # NOQA
    web[f"https://{WEBAPP}"] = lambda url: FakePage(
        url, "<html><head><title>Some page</title></head></html>")

    result = _invoke("login", WEBAPP)

    assert result.exit_code != 0
    assert "neither a dserver nor a dserver web interface" in result.output
    assert "Traceback" not in result.output


def test_web_interface_naming_missing_dserver_fails(config_path, web):  # NOQA
    web[f"https://{WEBAPP}"] = lambda url: FakePage(
        url, webapp_html("https://gone.example.org"))

    result = _invoke("login", WEBAPP)

    assert result.exit_code != 0
    assert "no dserver at https://gone.example.org" in result.output


def test_web_interface_pointing_to_plain_http_warns(config_path, web,  # NOQA
                                                    monkeypatch):
    monkeypatch.setattr(auth, "locate_dserver", lambda url: (
        "http://api.example.org", f"https://{WEBAPP}"))

    result = _invoke("login", WEBAPP, "--method", "ldap",
                     input="y\nbob\nx\n")

    assert "api.example.org is contacted over plain http" in result.output


def test_deep_link_of_web_interface(config_path, web):  # NOQA
    """A page that does not exist (no history fallback) falls back to the
    root page of the web interface."""
    web[f"https://{WEBAPP}"] = lambda url: FakePage(
        url, webapp_html(API) if url == f"https://{WEBAPP}/"
        else "Cannot GET", 200 if url == f"https://{WEBAPP}/" else 404)

    assert auth.find_dserver(f"https://{WEBAPP}/datasets/x") == API


def test_unreachable_server_reports_connection_error(config_path, web):  # NOQA
    result = _invoke("login", "https://nothing.example.org")
    assert result.exit_code != 0
    assert "Connection error" in result.output


@pytest.mark.parametrize("given, page, api, reason", [
    # Same host, encrypted: the web interface's own dserver.
    ("https://dtool.example.org", "https://dtool.example.org/",
     "https://dtool.example.org/api", None),
    ("https://example.org", "https://example.org/",
     "https://example.org:5000", None),
    # Local development: plain http on loopback is fine.
    ("http://127.0.0.1:8080", "http://127.0.0.1:8080/",
     "http://127.0.0.1:5000", None),
    # The page may have been altered on the way.
    ("http://lan-host:8080", "http://lan-host:8080/", "http://lan-host:5000",
     "without encryption"),
    # Redirected elsewhere.
    ("https://dtool.example.org", "https://evil.example.com/",
     "https://evil.example.com/api", "redirected"),
    # dserver on another host.
    ("https://dtool.example.org", "https://dtool.example.org/",
     "https://api.example.org", "different host"),
])
def test_confirmation_reason(given, page, api, reason):
    result = auth.confirmation_reason(given, page, api)
    if reason is None:
        assert result is None
    else:
        assert reason in result

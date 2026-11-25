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


# --- logging in with the address of the web interface ------------------------

WEBAPP = "dtool.example.org"
API = "https://api.example.org/dserver"


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

    import requests
    monkeypatch.setattr(requests, "request", request)
    monkeypatch.setattr(auth.time, "sleep", lambda s: None)
    pages[f"https://{WEBAPP}"] = lambda url: FakePage(url, webapp_html(API))
    return pages


def test_login_with_web_interface_address(config_path, web):  # NOQA
    """The address of the web interface, copied from the browser, works for
    logging in and in dserver:// URIs."""
    result = _invoke("login", f"https://{WEBAPP}/search?q=x#top",
                     "--method", "ldap", "--username", "bob",
                     input="secret\n")

    assert result.exit_code == 0, result.output
    assert f"web interface of the dserver at {API}" in result.output
    assert f"Logged in to {WEBAPP} as bob" in result.output
    config = _config(config_path)
    assert auth.token_claims(config[auth.token_key(WEBAPP)])["sub"] == "bob"
    assert config[f"DSERVER_URL_{WEBAPP}"] == API

    from dtool_dserver.connection import server_url
    assert server_url(WEBAPP) == API
    assert f"{WEBAPP} (dserver at {API}): bob" in _invoke("status").output

    result = _invoke("logout", WEBAPP)
    assert result.exit_code == 0
    assert _config(config_path) == {}


def test_login_with_web_interface_host_only(config_path, web):  # NOQA
    result = _invoke("login", WEBAPP, "--method", "ldap",
                     "--username", "bob", input="secret\n")
    assert result.exit_code == 0, result.output
    assert _config(config_path)[f"DSERVER_URL_{WEBAPP}"] == API


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
    monkeypatch.setattr(auth, "find_dserver",
                        lambda url: "http://api.example.org")

    result = _invoke("login", WEBAPP, "--method", "ldap", input="bob\nx\n")

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

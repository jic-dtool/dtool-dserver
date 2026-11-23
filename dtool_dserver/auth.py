"""Authentication with dserver: token lookup, storage, refresh and login.

Tokens are looked up per server, so that several dservers can be used at
once. For a server ``host[:port]``, the first of these is used:

1. ``DSERVER_TOKEN_<host[:port]>`` (environment or dtool config file), as
   stored by ``dtool dserver login``
2. ``DSERVER_TOKEN`` (environment or dtool config file), for all servers
3. ``DSERVER_TOKEN_FILE``, a file containing the token, for all servers

Tokens stored by ``dtool dserver login`` in the dtool config file are
refreshed automatically shortly before they expire, as long as the server's
maximum session age allows. Tokens given via environment variables are
never refreshed or written.
"""

import base64
import json
import logging
import os
import stat
import time

import requests
from dtoolcore.utils import (
    get_config_value,
    get_config_value_from_file,
    write_config_value_to_file,
)

from .connection import server_url
from .errors import DServerAuthenticationError, DServerStorageBrokerError

logger = logging.getLogger(__name__)

TOKEN_KEY_PREFIX = "DSERVER_TOKEN_"

# Stored tokens are refreshed when they expire within this time.
REFRESH_BEFORE_EXPIRY_SECONDS = 6 * 3600

DEVICE_CODE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"

# Timeout for requests to dserver (seconds)
TIMEOUT = 30


def token_key(server):
    """Return the config key of the token for a server (host[:port])."""
    return f"{TOKEN_KEY_PREFIX}{server}"


def _config_path(config_path):
    if config_path is None:
        # Looked up at call time, so that it can be changed (e.g. in tests).
        import dtoolcore.utils
        return dtoolcore.utils.DEFAULT_CONFIG_PATH
    return config_path


def token_claims(token):
    """Return the claims of a JWT without verifying its signature."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except (IndexError, ValueError):
        return {}


# --- lookup and storage ------------------------------------------------------

def lookup_token(server, config_path=None):
    """Return the token for a server; see module documentation."""
    config_path = _config_path(config_path)
    key = token_key(server)

    token = os.environ.get(key)
    if token:
        return token

    token = get_config_value_from_file(key, config_path=config_path)
    if token:
        return refresh_if_expiring(server, token, config_path=config_path)

    token = get_config_value("DSERVER_TOKEN", config_path=config_path)
    if token:
        return token

    token_file = get_config_value("DSERVER_TOKEN_FILE",
                                  config_path=config_path)
    if token_file and os.path.exists(token_file):
        with open(token_file) as fh:
            return fh.read().strip()

    raise DServerAuthenticationError(
        f"Not logged in to dserver {server}. Run "
        f"'dtool dserver login {server}', or set DSERVER_TOKEN (or "
        f"DSERVER_TOKEN_FILE pointing to a file containing the token) in the "
        f"environment or dtool config file."
    )


def store_token(server, token, config_path=None):
    """Store the token for a server in the dtool config file."""
    write_config_value_to_file(token_key(server), token,
                               config_path=_config_path(config_path))


def stored_token(server, config_path=None):
    """Return the token stored for a server in the dtool config file."""
    return get_config_value_from_file(token_key(server),
                                      config_path=_config_path(config_path))


def _read_config(config_path):
    if not os.path.isfile(config_path):
        return {}
    with open(config_path) as fh:
        return json.load(fh)


def remove_token(server, config_path=None):
    """Remove a stored token; return whether there was one."""
    config_path = _config_path(config_path)
    config = _read_config(config_path)
    if config.pop(token_key(server), None) is None:
        return False
    # Write with owner-only permissions from the start: the file holds tokens.
    fd = os.open(config_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                 stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(fd, "w") as fh:
        json.dump(config, fh, sort_keys=True, indent=2)
    os.chmod(config_path, stat.S_IRUSR | stat.S_IWUSR)
    return True


def stored_servers(config_path=None):
    """Return the servers with a token in the dtool config file."""
    config = _read_config(_config_path(config_path))
    return sorted(key[len(TOKEN_KEY_PREFIX):] for key in config
                  if key.startswith(TOKEN_KEY_PREFIX) and config[key])


# --- refresh -----------------------------------------------------------------

def refresh_if_expiring(server, token, config_path=None):
    """Refresh a stored token shortly before it expires.

    Returns the new token (and stores it), or the old token if it is not
    about to expire, has already expired, or cannot be refreshed (e.g. the
    server has no refresh endpoint, the session reached its maximum age, or
    the server is unreachable).
    """
    expires_at = token_claims(token).get("exp")
    if expires_at is None:
        return token
    remaining = expires_at - time.time()
    if remaining <= 0 or remaining > REFRESH_BEFORE_EXPIRY_SECONDS:
        return token

    try:
        response = requests.request(
            "POST", f"{server_url(server, config_path)}/auth/oauth2/refresh",
            json={"token": token}, timeout=TIMEOUT)
    except requests.exceptions.RequestException as e:
        logger.debug(f"Could not refresh token for {server}: {e}")
        return token
    if response.status_code != 200:
        logger.debug(f"Token for {server} not refreshed "
                     f"(HTTP {response.status_code}): {response.text}")
        return token

    new_token = response.json().get("token")
    if not new_token:
        return token
    store_token(server, new_token, config_path=config_path)
    logger.info(f"Refreshed token for dserver {server}")
    return new_token


# --- login -------------------------------------------------------------------

def _error_description(response):
    try:
        data = response.json()
    except ValueError:
        return response.text or f"HTTP {response.status_code}"
    return (data.get("error_description") or data.get("message")
            or data.get("msg") or data.get("error")
            or f"HTTP {response.status_code}")


def _request(method, url, **kwargs):
    try:
        return requests.request(method, url, timeout=TIMEOUT, **kwargs)
    except requests.exceptions.RequestException as e:
        from .connection import connection_error
        raise connection_error(url, e)


def available_methods(base_url):
    """Return the login methods a dserver offers ("oauth2", "ldap")."""
    methods = []
    response = _request("GET", f"{base_url}/auth/oauth2/info")
    if response.status_code == 200 and \
            response.json().get("configured", True):
        methods.append("oauth2")
    response = _request("GET", f"{base_url}/auth/ldap/info")
    if response.status_code == 200:
        methods.append("ldap")
    return methods


def device_login(base_url, client_name, notify, open_browser=None):
    """Log in with the OAuth 2.0 device authorization flow (RFC 8628).

    :param base_url: dserver URL (protocol://host[:port])
    :param client_name: name shown to the user when approving
    :param notify: called with (verification URL, user code) to show them
    :param open_browser: called with the verification URL, or None
    :returns: token
    """
    response = _request("POST", f"{base_url}/auth/oauth2/device",
                        json={"client_name": client_name})
    if response.status_code != 200:
        raise DServerAuthenticationError(
            f"Could not start login: {_error_description(response)}")
    device = response.json()

    uri = device.get("verification_uri_complete") or device["verification_uri"]
    notify(uri, device["user_code"])
    if open_browser is not None:
        open_browser(uri)

    interval = device.get("interval", 5)
    deadline = time.monotonic() + device.get("expires_in", 600)
    while True:
        time.sleep(interval)
        if time.monotonic() >= deadline:
            raise DServerAuthenticationError(
                "Login request expired, please try again.")
        response = _request(
            "POST", f"{base_url}/auth/oauth2/device/token",
            json={"grant_type": DEVICE_CODE_GRANT_TYPE,
                  "device_code": device["device_code"]})
        if response.status_code == 200:
            return response.json()["token"]
        try:
            error = response.json().get("error")
        except ValueError:
            error = None
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            interval += 5
            continue
        if error == "access_denied":
            raise DServerAuthenticationError("Login was denied.")
        if error == "expired_token":
            raise DServerAuthenticationError(
                "Login request expired, please try again.")
        raise DServerAuthenticationError(
            f"Login failed: {_error_description(response)}")


def ldap_login(base_url, username, password):
    """Log in with username and password (dserver LDAP token plugin)."""
    response = _request("POST", f"{base_url}/auth/ldap/token",
                        json={"username": username, "password": password})
    if response.status_code != 200 or "token" not in response.json():
        raise DServerAuthenticationError(
            f"Login failed: {_error_description(response)}")
    return response.json()["token"]


def whoami(base_url, token):
    """Return dserver's description of the token's user (GET /me)."""
    response = _request("GET", f"{base_url}/me",
                        headers={"Authorization": f"Bearer {token}"})
    if response.status_code != 200:
        raise DServerAuthenticationError(
            f"dserver rejected the token: {_error_description(response)}")
    return response.json()


__all__ = [
    "DServerAuthenticationError",
    "DServerStorageBrokerError",
    "available_methods",
    "device_login",
    "ldap_login",
    "lookup_token",
    "refresh_if_expiring",
    "remove_token",
    "store_token",
    "stored_servers",
    "stored_token",
    "token_claims",
    "token_key",
    "whoami",
]

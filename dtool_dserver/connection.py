"""Connection settings for dserver."""

import ipaddress
from urllib.parse import urlparse

from dtoolcore.utils import get_config_value

from .errors import DServerStorageBrokerError


def is_loopback(server):
    """Return True if server (host[:port]) is a loopback address."""
    host = urlparse(f"//{server}").hostname or ""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def protocol_key(server):
    """Return the config key of the protocol of a server (host[:port])."""
    return f"DSERVER_PROTOCOL_{server}"


def get_protocol(server, config_path=None):
    """Return the protocol (http or https) used to talk to dserver.

    Every request carries the user's token, so the default is https. Plain
    http is the default only for loopback hosts (e.g. a local development
    server). In order of precedence, the default is overridden by
    DSERVER_PROTOCOL_<host[:port]> (as stored by ``dtool dserver login
    http://...``) and DSERVER_PROTOCOL, each from the environment or the
    dtool config file.
    """
    for key in (protocol_key(server), "DSERVER_PROTOCOL"):
        protocol = get_config_value(key, config_path=config_path)
        if protocol is not None:
            break
    else:
        return "http" if is_loopback(server) else "https"
    if protocol not in ("http", "https"):
        raise DServerStorageBrokerError(
            f"Invalid {key} {protocol!r}, must be http or https")
    return protocol


def connection_error(url, error):
    """Return a DServerStorageBrokerError for a failed connection."""
    message = f"Connection error: {error}"
    if url.startswith("https://"):
        server = urlparse(url).netloc
        message += (
            f". If this dserver only serves plain HTTP, log in with "
            f"'dtool dserver login http://{server}' (note that the token is "
            f"then sent unencrypted)."
        )
    return DServerStorageBrokerError(message)


def server_url(server, config_path=None):
    """Return the base URL (protocol://host[:port]) of a dserver."""
    return f"{get_protocol(server, config_path=config_path)}://{server}"

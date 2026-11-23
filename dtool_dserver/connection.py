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


def get_protocol(server, config_path=None):
    """Return the protocol (http or https) used to talk to dserver.

    Every request carries the user's token, so the default is https. Plain
    http is the default only for loopback hosts (e.g. a local development
    server). DSERVER_PROTOCOL overrides the default.
    """
    default = "http" if is_loopback(server) else "https"
    protocol = get_config_value(
        'DSERVER_PROTOCOL', config_path=config_path, default=default)
    if protocol not in ("http", "https"):
        raise DServerStorageBrokerError(
            f"Invalid DSERVER_PROTOCOL {protocol!r}, must be http or https")
    return protocol


def connection_error(url, error):
    """Return a DServerStorageBrokerError for a failed connection."""
    message = f"Connection error: {error}"
    if url.startswith("https://"):
        message += (
            ". If this dserver only serves plain HTTP, set "
            "DSERVER_PROTOCOL=http (note that the token is then sent "
            "unencrypted)."
        )
    return DServerStorageBrokerError(message)


def server_url(server, config_path=None):
    """Return the base URL (protocol://host[:port]) of a dserver."""
    return f"{get_protocol(server, config_path=config_path)}://{server}"

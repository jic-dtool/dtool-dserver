"""``dtool dserver`` commands: log in to and out of dservers.

Registered with the dtool command line interface via the ``dtool.cli``
entry point.
"""

import datetime
import socket
import time
import webbrowser

import click

from . import auth
from .connection import is_loopback, server_url
from .errors import DServerStorageBrokerError


def _server(value):
    """Accept host[:port], a URL or a dserver:// URI.

    Returns host[:port] and the protocol if given as http:// or https://
    (else None).
    """
    protocol = None
    for prefix in ("dserver://", "https://", "http://"):
        if value.startswith(prefix):
            value = value[len(prefix):]
            if prefix != "dserver://":
                protocol = prefix[:-len("://")]
    return value.split("/", 1)[0], protocol


def _expiry(token):
    expires_at = auth.token_claims(token).get("exp")
    if expires_at is None:
        return "no expiry"
    when = datetime.datetime.fromtimestamp(expires_at).strftime(
        "%Y-%m-%d %H:%M")
    if expires_at <= time.time():
        return f"expired {when}"
    return f"valid until {when}"


@click.group()
def dserver():
    """Log in to and out of dserver instances."""


@dserver.command()
@click.argument("server")
@click.option("--method", type=click.Choice(["auto", "oauth2", "ldap"]),
              default="auto", show_default=True,
              help="Login method; 'auto' uses what the server offers.")
@click.option("--username", help="Username (LDAP login).")
@click.option("--no-browser", is_flag=True,
              help="Do not open a web browser (OAuth2 login).")
def login(server, method, username, no_browser):
    """Log in to SERVER (host[:port]) and store the token.

    With OAuth2 (e.g. ORCID), approve the login in a web browser, on this or
    any other machine. With LDAP, enter username and password.

    dserver is contacted over https (http for localhost). For a dserver that
    only serves plain http, log in to http://SERVER; dtool then remembers to
    use http for it.
    """
    server, protocol = _server(server)
    if protocol == "http" and not is_loopback(server):
        click.echo(f"Warning: {server} is contacted over plain http; your "
                   f"password or token is sent unencrypted.", err=True)
    try:
        base_url = f"{protocol}://{server}" if protocol else server_url(server)
        if method == "auto":
            methods = auth.available_methods(base_url)
            if not methods:
                raise click.ClickException(
                    f"No login method available on {server}. Is it a "
                    f"dserver with a token generator plugin?")
            method = methods[0]

        if method == "oauth2":
            def notify(uri, user_code):
                click.echo(f"To log in to {server}, open\n\n    {uri}\n\n"
                           f"in a web browser and approve the code "
                           f"{user_code}.\nWaiting for approval...")
            token = auth.device_login(
                base_url,
                client_name=f"dtool on {socket.gethostname()}"[:80],
                notify=notify,
                open_browser=None if no_browser else webbrowser.open)
        else:
            if username is None:
                username = click.prompt("Username")
            password = click.prompt("Password", hide_input=True)
            token = auth.ldap_login(base_url, username, password)

        user = auth.whoami(base_url, token)
    except DServerStorageBrokerError as e:
        raise click.ClickException(str(e))

    auth.store_token(server, token)
    if protocol is not None:
        auth.store_protocol(server, protocol)
    click.echo(f"Logged in to {server} as {user.get('username')} "
               f"({_expiry(token)}).")


@dserver.command()
@click.argument("server")
def logout(server):
    """Remove the stored token of SERVER."""
    server, _ = _server(server)
    auth.remove_protocol(server)
    if auth.remove_token(server):
        click.echo(f"Logged out of {server}.")
    else:
        click.echo(f"Not logged in to {server}.")


@dserver.command()
def status():
    """List the dservers you are logged in to."""
    servers = auth.stored_servers()
    if not servers:
        click.echo("Not logged in to any dserver.")
        return
    for server in servers:
        token = auth.stored_token(server)
        user = auth.token_claims(token).get("sub", "unknown user")
        name = f"{server} (http)" \
            if auth.stored_protocol(server) == "http" else server
        click.echo(f"{name}: {user}, {_expiry(token)}")

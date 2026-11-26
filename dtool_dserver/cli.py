"""``dtool dserver`` commands: log in to and out of dservers.

Registered with the dtool command line interface via the ``dtool.cli``
entry point.
"""

import datetime
import socket
import time
import webbrowser
from urllib.parse import urlsplit

import click

from . import auth
from .connection import get_protocol, is_loopback
from .errors import DServerStorageBrokerError


def _server(value):
    """Accept host[:port], a URL or a dserver:// URI.

    Returns host[:port], the protocol if given as http:// or https://
    (else None) and the path of a URL (else "").
    """
    if value.startswith(("http://", "https://")):
        url = urlsplit(value)
        return url.netloc, url.scheme, url.path.rstrip("/")
    if value.startswith("dserver://"):
        value = value[len("dserver://"):]
    return value.split("/", 1)[0], None, ""


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
@click.option("--yes", "-y", is_flag=True,
              help="Log in to the dserver a web interface names without "
                   "asking.")
def login(server, method, username, no_browser, yes):
    """Log in to SERVER and store the token.

    SERVER is the address of the dserver or of its web interface, e.g.
    dserver.example.com or https://dtool.example.com (copied from the
    browser). Then use dserver://SERVER/... URIs, as the web interface
    shows them; the host of the dserver works as well.

    The page of a web interface names its dserver. If that dserver is on
    another host, or the page was fetched over plain http, dtool asks
    before logging in (--yes to skip).

    With OAuth2 (e.g. ORCID), approve the login in a web browser, on this or
    any other machine. With LDAP, enter username and password.

    dserver is contacted over https (http for localhost). For a dserver that
    only serves plain http, log in to http://SERVER; dtool then remembers to
    use http for it.
    """
    server, protocol, path = _server(server)
    given = server
    url = f"{protocol or get_protocol(server)}://{server}{path}"
    try:
        base_url, page_url = auth.locate_dserver(url)
        if page_url is not None:
            click.echo(f"{url} is the web interface of the dserver at "
                       f"{base_url}.")
            reason = auth.confirmation_reason(url, page_url, base_url)
            if reason and not yes:
                click.echo(reason)
                click.confirm(f"Log in to {base_url}?", abort=True)
        # The token is stored for the dserver, whatever address was given;
        # the web interface's host stands for it (alias).
        api = urlsplit(base_url)
        server = api.netloc
        if api.scheme == "http" and not is_loopback(server):
            click.echo(f"Warning: {server} is contacted over plain http; "
                       f"your password or token is sent unencrypted.",
                       err=True)
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
    if base_url == f"{api.scheme}://{server}":
        auth.remove_url(server)
        auth.store_protocol(server, api.scheme)
    else:
        # The API is served under a path: dserver://SERVER/... URIs go to
        # base_url.
        auth.store_url(server, base_url)
        auth.remove_protocol(server)
    if given != server:
        # dserver://<web interface host>/... URIs go to the dserver as well.
        auth.remove_token(given)
        auth.remove_protocol(given)
        auth.store_url(given, base_url)
    click.echo(f"Logged in to {server} as {user.get('username')} "
               f"({_expiry(token)}).")
    if given != server:
        click.echo(f"dserver://{given}/... and dserver://{server}/... URIs "
                   f"both work, e.g. 'dtool ls dserver://{given}/'.")


@dserver.command()
@click.argument("server")
def logout(server):
    """Remove the stored token of SERVER."""
    server, _, _ = _server(server)
    target = auth.alias_target(server)
    removed = False
    for name in filter(None, [server, target]):
        auth.remove_protocol(name)
        auth.remove_url(name)
        removed = auth.remove_token(name) or removed
    if removed:
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
        api_url = auth.stored_url(server)
        if api_url:
            name = f"{server} (dserver at {api_url})"
        elif auth.stored_protocol(server) == "http":
            name = f"{server} (http)"
        else:
            name = server
        also = auth.aliases(server)
        if also:
            name += f" [also as {', '.join(also)}]"
        click.echo(f"{name}: {user}, {_expiry(token)}")

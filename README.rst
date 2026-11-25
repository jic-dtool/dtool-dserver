dtool-dserver
=============

.. image:: https://github.com/jic-dtool/dtool-dserver/raw/python-coverage-comment-action-data/badge.svg
   :target: https://github.com/jic-dtool/dtool-dserver/tree/python-coverage-comment-action-data
   :alt: Coverage

A dtool storage broker that accesses datasets through a dserver instance
using signed URLs.

This broker allows users to access datasets stored on S3, Azure, or other
backends without needing direct credentials for those backends. Instead,
the dserver generates time-limited signed URLs on behalf of the user.

Features
--------

- Read datasets through dserver signed URLs
- Create new datasets through dserver signed URLs
- Automatic caching of downloaded items
- Support for all dtool operations (ls, cp, info, item fetch, etc.)
- Backend-agnostic (works with any storage backend dserver supports)

Getting started
---------------

1. Install the dtool command line tools with this broker::

       pip install "dtool>=3.28" dtool-dserver

2. Log in to your dserver, once per machine, with the address of its web
   interface as you see it in your browser::

       dtool dserver login https://dserver.example.com

   With OAuth2 (e.g. ORCID), dtool opens the dserver web interface in your
   browser and shows a short code. Sign in there; the web interface asks you
   to approve "dtool on <your machine>". Check that the code matches the one
   in your terminal and click *Approve*. On a remote machine (e.g. over SSH),
   add ``--no-browser`` and open the printed link on any other device. With
   LDAP, enter your username and password instead.

3. Use ``dserver://`` URIs with the same address with any dtool command::

       dtool ls dserver://dserver.example.com/
       dtool ls dserver://dserver.example.com/s3/my-bucket
       dtool cp ./my-dataset dserver://dserver.example.com/s3/my-bucket
       dtool cp dserver://dserver.example.com/s3/my-bucket/<uuid> ./downloads

   The first lists all datasets you have access to, with their URIs. The web
   interface shows these URIs and ``dtool cp`` commands for each dataset
   (*Copy*).

You need no credentials for the storage (S3, Azure) itself: dserver hands out
signed URLs. What you can list and download (search permission) and upload
(register permission) for a storage location is decided by the dserver's
administrator.

Your login is kept in the dtool config file and renewed automatically while
you use it, for up to a week (depending on the dserver); then run
``dtool dserver login`` again. See Authentication for details.

Installation
------------

.. code-block:: bash

    pip install "dtool>=3.28" dtool-dserver

``dtool`` installs the command line tools (``dtool cp``, ``dtool ls``, ...);
3.28 or later is needed on Python 3.12 and later (dtool-cli 0.7.2). The
broker alone, without command line, is ``pip install dtool-dserver``.

URI Format
----------

The URI format encodes both the dserver and the backend storage location::

    dserver://<server>/<backend>/<bucket_or_container>/<uuid>

``<server>`` is the host (and port) you logged in to: the dserver itself or
its web interface. ``dserver://<server>/`` stands for all storage locations
you can search, for ``dtool ls``.

Examples:

- ``dserver://localhost:5000/s3/my-bucket/550e8400-e29b-41d4-a716-446655440000``
- ``dserver://dserver.example.com/azure/my-container/dataset-uuid``

Usage
-----

List datasets::

    dtool ls dserver://localhost:5000/s3/my-bucket/

Copy a dataset to local storage::

    dtool cp dserver://localhost:5000/s3/my-bucket/uuid /local/path/

Create a new dataset::

    dtool create dserver://localhost:5000/s3/my-bucket/new-dataset

Authentication
--------------

Log in once per dserver; the token is stored in the dtool config file
(readable only by you) and used for all ``dserver://<server>/...`` URIs::

    dtool dserver login dserver.example.com

``<server>`` can be the address of the dserver web interface, including a
URL copied from the browser (e.g. ``https://dserver.example.com/``), or of
the dserver API itself; use the same host in ``dserver://`` URIs. With the
address of the web interface, dtool looks up the dserver API it uses and
remembers it.

How you log in depends on the dserver:

- **OAuth2** (e.g. ORCID): dtool shows a short code and a link. Open the link
  in a web browser, on this or any other machine (handy over SSH), log in as
  usual and approve the code. Use ``--no-browser`` to not open a browser
  automatically.
- **LDAP**: enter your username and password
  (``--username`` skips the username prompt).

If a dserver offers both, choose with ``--method oauth2`` or
``--method ldap``. You must be registered as a user in the dserver; ask its
administrator otherwise.

Tokens are valid for a day (depending on the dserver) and are refreshed
automatically when they are about to expire, up to the dserver's maximum
session length (by default a week after logging in). After that, log in
again.

Other commands::

    dtool dserver status                          # servers you are logged in to
    dtool dserver logout dserver.example.com      # remove the stored token

Setting up a dserver for command-line logins
--------------------------------------------

For administrators. ``dtool dserver login`` needs on the server side:

- **OAuth2 logins**: ``dserver-token-generator-plugin-oauth2`` with the device
  authorization flow. It stores pending logins in dserver's SQL database;
  create its table with ``flask db migrate`` and ``flask db upgrade`` after
  installing or upgrading the plugin. ``OAUTH2_DEVICE_VERIFICATION_URL`` (or
  ``OAUTH2_FRONTEND_URL``) must point to the web interface, where users
  approve logins.
- **The web interface**: a dtool-lookup-webapp version with the login
  approval dialog (newer than 0.4.0). Versions that name their dserver in
  the page (``<meta name="dserver-url">``, from
  ``VUE_APP_DTOOL_LOOKUP_SERVER_URL``) let users log in with the address of
  the web interface. Point it to the plugin's endpoints
  under ``/auth/oauth2`` with ``VUE_APP_OAUTH2_LOGIN_URL`` (``.../login``),
  ``VUE_APP_DTOOL_LOOKUP_SERVER_TOKEN_GENERATOR_URL`` (``.../token``) and
  ``VUE_APP_DTOOL_LOOKUP_SERVER_AUTH_LOGOUT_URL`` (``.../logout``); the device
  approval endpoints (``.../device``) are found by default.
- **LDAP logins**: ``dserver-token-generator-plugin-ldap``.
- **Token claims**: dserver accepts only tokens with audience and issuer
  ``dserver`` by default (``JWT_DECODE_AUDIENCE`` / ``JWT_DECODE_ISSUER``);
  both plugins issue them.
- **Session length**: tokens last ``JWT_TOKEN_EXPIRY_HOURS`` (default 24) and
  are refreshed up to ``JWT_MAX_SESSION_HOURS`` (default 168) after the
  browser login.
- **Users and permissions**: users need search permission on a base URI to
  list and download, register permission to upload (``flask user
  search_permission`` / ``flask user register_permission``, or automatically
  on first login where the plugin provisions users).
- **https**: the CLI contacts dservers over https (except ``localhost``).

Advanced configuration (optional)
---------------------------------

Nothing needs to be configured: ``dtool dserver login`` stores everything
dtool needs. The following settings are for special cases.

Tokens without logging in, e.g. in scripts or CI. For a dserver
``host[:port]``, the first of these is used (environment or dtool config
file ``~/.config/dtool/dtool.json``):

1. ``DSERVER_TOKEN_<host[:port]>``; this is where ``dtool dserver login``
   stores the token
2. ``DSERVER_TOKEN``, for all dservers
3. ``DSERVER_TOKEN_FILE``, a file containing the token, for all dservers

Tokens from environment variables are never refreshed or stored. In the web
interface (dtool-lookup-webapp), "Copy token to clipboard" in the user menu
gives you a token, e.g. for ``DSERVER_TOKEN``.

Plain http: dserver is contacted over https, except for ``localhost``,
``127.0.0.1`` and ``::1``. For a dserver that only serves plain http, e.g. on
your local network, log in with ``dtool dserver login http://<server>``; dtool
remembers to use http for this server (``DSERVER_PROTOCOL_<host[:port]>`` in
the dtool config file) until you log in with ``https://`` or log out. Your
password and token are then sent unencrypted, so do this only for a dserver
you trust on a network you trust. ``DSERVER_PROTOCOL`` sets the protocol for
all dservers.

dserver API address: ``DSERVER_URL_<host[:port]>`` is the base URL of the
dserver API that ``dserver://<host[:port]>/...`` URIs go to, e.g.
``https://example.org/dserver``. ``dtool dserver login`` stores it when you
log in with the address of the web interface. It takes precedence over
``DSERVER_PROTOCOL_<host[:port]>``.

Download cache: downloaded items are cached in ``dtool-dserver-cache`` in the
system's temporary directory; set ``DSERVER_CACHE_DIR`` (environment or dtool
config file) to use another directory.

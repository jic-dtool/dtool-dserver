dtool-dserver
=============

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

Installation
------------

.. code-block:: bash

    pip install dtool-dserver

The ``dtool dserver`` commands (login, logout, status) need the dtool command
line interface, ``pip install "dtool-cli>=0.7.2"``; older releases do not
start on Python 3.12 and later.

Configuration
-------------

Settings are read from the environment or the dtool config file
(``~/.config/dtool/dtool.json``):

- ``DSERVER_TOKEN_<host[:port]>``: token for one dserver, as stored by
  ``dtool dserver login`` (see Authentication)
- ``DSERVER_TOKEN``: token used for all dservers without their own token
- ``DSERVER_TOKEN_FILE``: alternatively, path to a file containing the token
- ``DSERVER_PROTOCOL``: Protocol to use (http or https). Default: https, as
  every request carries the token; http for loopback hosts (``localhost``,
  ``127.0.0.1``, ``::1``), e.g. a local development server
- ``DSERVER_CACHE_DIR``: Cache directory for downloaded items
  (default: system temp directory)

URI Format
----------

The URI format encodes both the dserver endpoint and the backend storage
location::

    dserver://<server>/<backend>/<bucket_or_container>/<uuid>

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

Tokens can also be provided without logging in, e.g. in scripts or CI. For a
dserver ``host[:port]``, the first of these is used:

1. ``DSERVER_TOKEN_<host[:port]>`` (environment or dtool config file); this is
   where ``dtool dserver login`` stores the token
2. ``DSERVER_TOKEN`` (environment or dtool config file), for all dservers
3. ``DSERVER_TOKEN_FILE``, a file containing the token, for all dservers

Tokens from environment variables are never refreshed or stored. In the web
interface (dtool-lookup-webapp), "Copy token to clipboard" in the user menu
gives you a token, e.g. for ``DSERVER_TOKEN``.

dserver is contacted over https, except for ``localhost``; set
``DSERVER_PROTOCOL=http`` only for servers you trust on your local network,
as the token is then sent unencrypted.

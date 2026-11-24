Changelog
=========

0.1.0 (2026-11-24)
------------------

Initial release: a dtool storage broker for ``dserver://`` URIs, which reads
and writes datasets through signed URLs issued by dserver, without
credentials for the storage backend (S3, Azure, ...).

Command line

* ``dtool dserver login | logout | status``. OAuth2 dservers use the device
  authorization flow: approve a short code in the dserver web interface, on
  this or any other machine (``--no-browser`` over SSH). LDAP dservers prompt
  for username and password. The token is checked with dserver before it is
  stored.
* Tokens are stored per dserver in the dtool config file (owner-only
  permissions), so several dservers can be used at once, and refreshed
  automatically while in use, up to the dserver's maximum session age.

Configuration (nothing needs to be configured after logging in)

* Token lookup per dserver ``host[:port]``: ``DSERVER_TOKEN_<host[:port]>``
  (stored by ``dtool dserver login``), then ``DSERVER_TOKEN``, then
  ``DSERVER_TOKEN_FILE``, each from the environment or the dtool config file.
  Tokens from environment variables are never refreshed or written.
* dserver is contacted over https, as every request carries the user's
  token; http only for loopback hosts (``localhost``, ``127.0.0.1``,
  ``::1``). ``dtool dserver login http://<server>`` remembers plain http for
  that server (``DSERVER_PROTOCOL_<host[:port]>``, warning that credentials
  are sent unencrypted); ``login https://<server>`` and ``logout`` forget it.
  ``DSERVER_PROTOCOL`` sets the protocol for all dservers; invalid values are
  rejected. A failed https connection suggests logging in over http.
* ``DSERVER_CACHE_DIR``: cache directory for downloaded items (environment
  or dtool config file).

Documentation

* README: "Getting started" for users (install, log in, copy), setup of a
  dserver for command-line logins for administrators, and optional settings.

Requirements and packaging

* Python 3.10 or later; ``dtoolcore>=3.20.0``, ``click``, ``requests``. The
  ``dtool dserver`` commands need ``dtool-cli>=0.7.2`` (e.g. ``dtool>=3.28``).
* Built with ``hatchling`` and ``hatch-vcs``; the version is derived from git
  tags.

Tests and CI

* Unit tests on Python 3.10-3.14.
* End-to-end tests against a running dserver with S3 (SeaweedFS) storage:
  upload, read, list and download through signed URLs.
* End-to-end tests of the command line with real logins: browser login at a
  mock OAuth2 provider approving ``dtool dserver login``, LDAP login against
  OpenLDAP (with user creation on first login), automatic token refresh, and
  ``dtool cp`` up and down compared with ``dtool diff --full``, README, tags
  and annotations.
* Code coverage of unit and end-to-end tests combined (including the
  ``dtool`` commands run as subprocesses), at least 85 % required; reported
  on pull requests and as a badge.

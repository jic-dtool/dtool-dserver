Changelog
=========

Unreleased
----------

* ``dtool dserver login | logout | status`` commands. OAuth2 dservers use the
  device authorization flow (approve a short code in the web interface, also
  from another machine), LDAP dservers prompt for username and password.
* Tokens per dserver: ``DSERVER_TOKEN_<host[:port]>`` (stored by
  ``dtool dserver login`` in the dtool config file) takes precedence over
  ``DSERVER_TOKEN`` and ``DSERVER_TOKEN_FILE``, so several dservers can be
  used at once.
* Stored tokens are refreshed automatically when they expire within 6 hours
  (up to the dserver's maximum session age); tokens from environment
  variables are never refreshed or written.
* Requires ``dtoolcore>=3.20.0`` (config file written with owner-only
  permissions) and ``click``.
* **Breaking:** dserver is contacted over https by default (previously http),
  as every request carries the user's token. Loopback hosts (``localhost``,
  ``127.0.0.1``, ``::1``) keep http by default; ``DSERVER_PROTOCOL`` overrides.
  A failed https connection suggests ``DSERVER_PROTOCOL=http``, and invalid
  ``DSERVER_PROTOCOL`` values are rejected.
* End-to-end tests (``tests/test_e2e.py``) and CI job uploading, reading,
  listing and downloading a dataset through a running dserver with S3
  (SeaweedFS) storage. CI also runs the unit tests now (previously only
  lint and an import check), on Python 3.10-3.14.
* End-to-end test of the command line (``tests/test_e2e_cli.py``):
  ``dtool dserver login`` through the device flow of the OAuth2 token
  generator plugin, ``dtool cp`` up and down with only the stored token,
  and ``dtool dserver logout``.
* End-to-end CI of the command line with real logins: browser login at a mock
  OAuth2 provider approving ``dtool dserver login``, LDAP password login
  against OpenLDAP (with user creation on first login), automatic token
  refresh, and ``dtool cp`` up and down compared with ``dtool diff --full``,
  README, tags and annotations.
* README: "Getting started" walkthrough for users (install, log in, copy)
  and "Setting up a dserver for command-line logins" for administrators.

0.1.0 (initial release)
-----------------------

* Requires Python 3.10 or later.
* Initial release.
* Built with ``hatchling`` and ``hatch-vcs``; the version is derived from git tags.


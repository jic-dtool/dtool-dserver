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

0.1.0 (initial release)
-----------------------

* Requires Python 3.10 or later.
* Initial release.
* Built with ``hatchling`` and ``hatch-vcs``; the version is derived from git tags.


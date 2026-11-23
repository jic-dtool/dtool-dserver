Changelog
=========

Unreleased
----------

* **Breaking:** dserver is contacted over https by default (previously http),
  as every request carries the user's token. Loopback hosts (``localhost``,
  ``127.0.0.1``, ``::1``) keep http by default; ``DSERVER_PROTOCOL`` overrides.
  A failed https connection suggests ``DSERVER_PROTOCOL=http``, and invalid
  ``DSERVER_PROTOCOL`` values are rejected.

0.1.0 (initial release)
-----------------------

* Initial release.


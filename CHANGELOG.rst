Changelog
=========

Unreleased
----------

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


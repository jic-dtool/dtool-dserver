"""URI parsing and generation: full dserver://server/backend/bucket[/uuid]
format is mandatory (dserver://server/ only for listing); everything else
must be rejected loudly."""

import pytest
import requests

from dtool_dserver.storagebroker import DServerStorageBroker

from . import conftest as cf


def test_parse_dataset_uri():
    broker = DServerStorageBroker(cf.DATASET_URI)
    assert broker.uuid == cf.UUID
    assert broker._server == cf.SERVER
    assert broker._backend_base_uri == "s3://my-bucket"
    assert broker._backend_uri == f"s3://my-bucket/{cf.UUID}"
    assert broker.data_key_prefix == f"{cf.UUID}/data/"


def test_parse_base_uri():
    broker = DServerStorageBroker(cf.BUCKET_BASE)
    assert broker.uuid is None
    assert broker._backend_base_uri == "s3://my-bucket"
    assert broker._backend_uri is None


@pytest.mark.parametrize("uri", [
    f"dserver://{cf.SERVER}",
    f"dserver://{cf.SERVER}/",
])
def test_parse_server_uri(uri, monkeypatch):
    """dserver://server/ lists all datasets; it is not a dataset."""
    monkeypatch.setenv("DSERVER_TOKEN", "test-token")
    broker = DServerStorageBroker(uri)
    assert broker.uuid is None
    assert broker._backend_base_uri is None
    assert broker.has_admin_metadata() is False


@pytest.mark.parametrize("bad_uri", [
    f"dserver://{cf.SERVER}/{cf.UUID}",             # legacy short format
    f"dserver://{cf.SERVER}/s3/bucket/extra/{cf.UUID}",  # too many parts
    "dserver:///s3/bucket",                         # missing server
    f"http://{cf.SERVER}/s3/bucket/{cf.UUID}",      # wrong scheme
])
def test_parse_rejects_invalid_uris(bad_uri):
    with pytest.raises(ValueError):
        DServerStorageBroker(bad_uri)


def test_generate_uri_always_full_format(monkeypatch):
    # Even with a default-base-URI-style env var set, the full format
    # must be emitted (legacy shortening must not come back).
    monkeypatch.setenv("DSERVER_DEFAULT_BASE_URI", "s3://my-bucket")
    uri = DServerStorageBroker.generate_uri(
        "name", cf.UUID, cf.BUCKET_BASE + "/")
    assert uri == cf.DATASET_URI


@pytest.mark.parametrize("bad_base", [
    f"dserver://{cf.SERVER}/",
    f"dserver://{cf.SERVER}/just-one",
    f"dserver://{cf.SERVER}/s3/bucket/uuid",
])
def test_generate_uri_rejects_non_base_uris(bad_base, monkeypatch):
    def no_network(*args, **kwargs):
        raise requests.exceptions.ConnectionError("no network in tests")
    monkeypatch.setattr(requests, "request", no_network)
    with pytest.raises(ValueError):
        DServerStorageBroker.generate_uri("name", cf.UUID, bad_base)


def test_has_admin_metadata_false_for_base_uri(monkeypatch):
    monkeypatch.setenv("DSERVER_TOKEN", "test-token")
    broker = DServerStorageBroker(cf.BUCKET_BASE)
    assert broker.has_admin_metadata() is False


def test_copy_to_server_uri_names_storage_locations(monkeypatch):
    """`dtool cp ... dserver://server/` needs a storage location; the error
    names those the user has access to."""
    monkeypatch.setenv("DSERVER_TOKEN", "test-token")
    requested = []

    def fake_request(method, url, **kwargs):
        requested.append((method, url))
        return cf.FakeResponse([{"base_uri": "s3://bucket-a"},
                                {"base_uri": "azure://container-b"}])

    monkeypatch.setattr(requests, "request", fake_request)
    with pytest.raises(ValueError) as excinfo:
        DServerStorageBroker.generate_uri(
            "name", cf.UUID, f"dserver://{cf.SERVER}/")
    assert requested == [("GET", f"https://{cf.SERVER}/base-uris")]
    assert f"dserver://{cf.SERVER}/s3/bucket-a, " \
        f"dserver://{cf.SERVER}/azure/container-b" in str(excinfo.value)

"""End-to-end tests against a running dserver with S3 storage.

Nothing is mocked: datasets are uploaded to and downloaded from S3 through
signed URLs issued by dserver (dserver-signed-url-plugin). CI runs these
against a minimal dserver backed by SeaweedFS and MongoDB, see
.github/workflows/test.yml and ci/setup_dserver.py.

They are skipped unless DTOOL_DSERVER_E2E_BASE_URI is set to a base URI the
user of DSERVER_TOKEN may search and register on, e.g.
``dserver://localhost:5000/s3/dtool-test``.
"""

import os

import pytest

E2E_BASE_URI = os.environ.get("DTOOL_DSERVER_E2E_BASE_URI")

pytestmark = pytest.mark.skipif(
    not E2E_BASE_URI,
    reason="set DTOOL_DSERVER_E2E_BASE_URI to run against a live dserver",
)

README = "---\ndescription: End-to-end test dataset\nauthor: Jürgen Müller\n"
ITEMS = {
    "hello.txt": b"Hello, dserver!\n",
    "nested/dir/values.bin": bytes(range(256)) * 16,
    "unicode/grüße.txt": "Grüße aus Freiburg\n".encode("utf-8"),
    "empty.txt": b"",
}


@pytest.fixture
def local_dataset(tmp_path):
    """Create a frozen dataset on local disk and return it."""
    import dtoolcore

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    base_dir = tmp_path / "local"
    base_dir.mkdir()

    with dtoolcore.DataSetCreator("e2e-dataset", str(base_dir)) as creator:
        for relpath, content in ITEMS.items():
            fpath = source_dir / relpath.replace("/", "_")
            fpath.write_bytes(content)
            handle = creator.put_item(str(fpath), relpath)
            creator.add_item_metadata(handle, "size", len(content))
        creator.put_readme(README)
        creator.put_annotation("project", "dtool-dserver-e2e")
        creator.put_tag("e2e")
        uri = creator.uri

    return dtoolcore.DataSet.from_uri(uri)


def _content(dataset, identifier):
    with open(dataset.item_content_abspath(identifier), "rb") as fh:
        return fh.read()


def test_upload_read_list_and_download(local_dataset, tmp_path):
    import dtoolcore
    from dtoolcore.compare import diff_content, diff_identifiers, diff_sizes

    # Upload: dtool cp to dserver, i.e. signed upload URLs and
    # upload-complete.
    remote_uri = dtoolcore.copy(local_dataset.uri, E2E_BASE_URI)
    assert remote_uri == f"{E2E_BASE_URI}/{local_dataset.uuid}"

    # Read through dserver's signed read URLs.
    remote = dtoolcore.DataSet.from_uri(remote_uri)
    assert remote.uuid == local_dataset.uuid
    assert remote.name == "e2e-dataset"
    assert remote.admin_metadata["frozen_at"] == \
        local_dataset.admin_metadata["frozen_at"]
    assert remote.get_readme_content() == README
    assert remote.list_tags() == ["e2e"]
    assert remote.get_annotation("project") == "dtool-dserver-e2e"
    assert remote.list_overlay_names() == ["size"]
    assert remote.get_overlay("size") == local_dataset.get_overlay("size")

    assert set(remote.identifiers) == set(local_dataset.identifiers)
    for identifier in local_dataset.identifiers:
        local_properties = local_dataset.item_properties(identifier)
        remote_properties = remote.item_properties(identifier)
        for key in ("relpath", "size_in_bytes", "hash"):
            assert remote_properties[key] == local_properties[key]
        assert _content(remote, identifier) == \
            ITEMS[local_properties["relpath"]]

    # The dataset is listed in its base URI.
    listed = [ds.uri for ds in dtoolcore.iter_datasets_in_base_uri(
        E2E_BASE_URI)]
    assert remote_uri in listed

    # Download: dtool cp from dserver to local disk.
    download_dir = tmp_path / "download"
    download_dir.mkdir()
    downloaded_uri = dtoolcore.copy(remote_uri, str(download_dir))
    downloaded = dtoolcore.DataSet.from_uri(downloaded_uri)
    assert downloaded.uuid == local_dataset.uuid
    assert diff_identifiers(local_dataset, downloaded) == []
    assert diff_sizes(local_dataset, downloaded) == []
    assert diff_content(local_dataset, downloaded) == []
    assert downloaded.get_readme_content() == README
    assert downloaded.get_overlay("size") == local_dataset.get_overlay("size")


def test_copying_the_same_dataset_twice_fails(local_dataset):
    """A dataset can only be registered once under a base URI."""
    import dtoolcore

    dtoolcore.copy(local_dataset.uri, E2E_BASE_URI)
    with pytest.raises(Exception):
        dtoolcore.copy(local_dataset.uri, E2E_BASE_URI)

"""End-to-end test of the dtool command line against a running dserver.

Logs in with ``dtool dserver login`` (OAuth 2.0 device authorization flow of
dserver-token-generator-plugin-oauth2), copies a dataset to dserver and back
with ``dtool cp`` using only the stored token, and logs out again. The
approval that a user would give in the webapp is sent directly to the API,
with the token in DSERVER_TOKEN_FILE as the logged-in web user.

Like tests/test_e2e.py, this is skipped unless DTOOL_DSERVER_E2E_BASE_URI is
set. It needs the ``dtool`` command (dtool-cli>=0.7.2, with dtool-create
and dtool-info for ``dtool cp`` and ``dtool ls``) and a dserver with
the OAuth2 token generator plugin; see .github/workflows/test.yml.
"""

import json
import os
import re
import shutil
import stat
import subprocess
import sys

import pytest

E2E_BASE_URI = os.environ.get("DTOOL_DSERVER_E2E_BASE_URI")

pytestmark = pytest.mark.skipif(
    not E2E_BASE_URI,
    reason="set DTOOL_DSERVER_E2E_BASE_URI to run against a live dserver",
)

ITEMS = {
    "hello.txt": b"Hello from the command line!\n",
    "nested/values.bin": bytes(range(256)) * 4,
}

TIMEOUT = 120


@pytest.fixture
def server():
    """host:port of the dserver in E2E_BASE_URI."""
    return E2E_BASE_URI[len("dserver://"):].split("/", 1)[0]


@pytest.fixture
def web_token():
    """Token of the user approving the login, as the webapp would send it."""
    with open(os.environ["DSERVER_TOKEN_FILE"]) as fh:
        return fh.read().strip()


@pytest.fixture
def cli_env(tmp_path):
    """Environment of a user who has not logged in to any dserver yet.

    HOME points to an empty directory, so the dtool config file is
    $HOME/.config/dtool/dtool.json, and no token is set in the environment.
    """
    if shutil.which("dtool") is None:
        pytest.fail("the dtool command is not installed (dtool-cli)")
    home = tmp_path / "home"
    home.mkdir()
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("DSERVER_TOKEN")}
    env["HOME"] = str(home)
    # Read the output of the login line by line while it waits.
    env["PYTHONUNBUFFERED"] = "1"
    return env


@pytest.fixture
def local_dataset(tmp_path):
    import dtoolcore

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    base_dir = tmp_path / "local"
    base_dir.mkdir()
    with dtoolcore.DataSetCreator("cli-dataset", str(base_dir)) as creator:
        for relpath, content in ITEMS.items():
            fpath = source_dir / relpath.replace("/", "_")
            fpath.write_bytes(content)
            creator.put_item(str(fpath), relpath)
        creator.put_readme("---\ndescription: dtool CLI end-to-end test\n")
        uri = creator.uri
    return dtoolcore.DataSet.from_uri(uri)


def dtool(env, *args, check=True):
    result = subprocess.run(["dtool", *args], env=env, capture_output=True,
                            text=True, timeout=TIMEOUT)
    if check and result.returncode != 0:
        pytest.fail(f"dtool {' '.join(args)} failed:\n"
                    f"{result.stdout}\n{result.stderr}")
    return result


def login(env, server, web_token):
    """Run 'dtool dserver login' and approve its code; return its output."""
    import requests

    process = subprocess.Popen(
        ["dtool", "dserver", "login", server, "--no-browser"], env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        output = ""
        user_code = None
        for line in process.stdout:
            output += line
            match = re.search(r"approve the code ([A-Z]{4}-[A-Z]{4})", line)
            if match:
                user_code = match.group(1)
                break
        assert user_code is not None, f"No user code in output:\n{output}"

        # What the webapp does when the user clicks "Approve".
        url = f"http://{server}/auth/oauth2/device/{user_code}"
        headers = {"Authorization": f"Bearer {web_token}"}
        request = requests.get(url, headers=headers, timeout=10)
        assert request.status_code == 200, request.text
        assert request.json()["status"] == "pending"
        assert request.json()["client_name"].startswith("dtool on ")
        response = requests.post(f"{url}/approve", headers=headers,
                                 timeout=10)
        assert response.status_code == 200, response.text

        output += process.stdout.read()
        assert process.wait(timeout=TIMEOUT) == 0, output
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
    return output


def test_login_copy_and_logout(server, web_token, cli_env, local_dataset,
                               tmp_path):
    import dtoolcore

    # Not logged in yet: the error tells the user how to log in.
    result = dtool(cli_env, "ls", E2E_BASE_URI, check=False)
    assert result.returncode != 0
    assert f"dtool dserver login {server}" in result.stdout + result.stderr

    output = login(cli_env, server, web_token)
    assert f"Logged in to {server} as" in output

    # The token is stored per server in the dtool config file, readable
    # only by the user.
    config_path = os.path.join(cli_env["HOME"], ".config", "dtool",
                               "dtool.json")
    with open(config_path) as fh:
        config = json.load(fh)
    assert f"DSERVER_TOKEN_{server}" in config
    if sys.platform != "win32":
        assert stat.S_IMODE(os.stat(config_path).st_mode) == 0o600

    result = dtool(cli_env, "dserver", "status")
    assert result.stdout.startswith(f"{server}: ")
    assert "valid until" in result.stdout

    # Upload and download with dtool cp, authenticated by the stored token.
    remote_uri = dtool(cli_env, "cp", local_dataset.uri,
                       E2E_BASE_URI).stdout.strip().splitlines()[-1]
    assert remote_uri == f"{E2E_BASE_URI}/{local_dataset.uuid}"
    assert remote_uri in dtool(cli_env, "ls", E2E_BASE_URI).stdout

    download_dir = tmp_path / "download"
    download_dir.mkdir()
    downloaded_uri = dtool(cli_env, "cp", remote_uri,
                           str(download_dir)).stdout.strip().splitlines()[-1]
    downloaded = dtoolcore.DataSet.from_uri(downloaded_uri)
    assert downloaded.uuid == local_dataset.uuid
    for identifier in downloaded.identifiers:
        relpath = downloaded.item_properties(identifier)["relpath"]
        with open(downloaded.item_content_abspath(identifier), "rb") as fh:
            assert fh.read() == ITEMS[relpath]
    assert len(downloaded.identifiers) == len(ITEMS)

    # After logging out, the token is gone and dserver is out of reach.
    result = dtool(cli_env, "dserver", "logout", server)
    assert f"Logged out of {server}" in result.stdout
    with open(config_path) as fh:
        assert f"DSERVER_TOKEN_{server}" not in json.load(fh)
    result = dtool(cli_env, "ls", E2E_BASE_URI, check=False)
    assert result.returncode != 0
    assert f"dtool dserver login {server}" in result.stdout + result.stderr

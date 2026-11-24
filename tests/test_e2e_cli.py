"""End-to-end tests of the dtool command line against a running dserver.

Everything goes through the ``dtool`` command, with the stored token as the
only credentials:

- OAuth2: the user logs in at the OAuth2 provider in a "browser" (a mock
  provider in CI, followed with plain HTTP requests), and with that session
  approves the code of ``dtool dserver login`` (device authorization flow),
  as the webapp does. The stored token is refreshed automatically.
- LDAP: ``dtool dserver login --method ldap`` with username and password; a
  user unknown to dserver is created on the first login.

Both copy a dataset to dserver and back with ``dtool cp`` and compare it with
``dtool diff --full``, README, tags and annotations.

Like tests/test_e2e.py, this is skipped unless DTOOL_DSERVER_E2E_BASE_URI is
set. It needs the ``dtool`` command (dtool-cli>=0.7.2, dtool-create,
dtool-info, dtool-tag, dtool-annotation) and a dserver with the OAuth2 and
LDAP token generator plugins; see .github/workflows/test.yml.
"""

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from urllib.parse import urljoin

import pytest

E2E_BASE_URI = os.environ.get("DTOOL_DSERVER_E2E_BASE_URI")

pytestmark = pytest.mark.skipif(
    not E2E_BASE_URI,
    reason="set DTOOL_DSERVER_E2E_BASE_URI to run against a live dserver",
)

ITEMS = {
    "hello.txt": b"Hello from the command line!\n",
    "nested/values.bin": bytes(range(256)) * 4,
    "unicode/grüße.txt": "Grüße aus Freiburg\n".encode("utf-8"),
    "empty.txt": b"",
}
README = "---\ndescription: dtool CLI end-to-end test\n"
TAGS = ["cli", "e2e"]
ANNOTATIONS = {"project": "dtool-dserver-e2e", "replicates": 3}

TIMEOUT = 120


# --- fixtures and helpers ----------------------------------------------------

@pytest.fixture
def server():
    """host:port of the dserver in E2E_BASE_URI."""
    return E2E_BASE_URI[len("dserver://"):].split("/", 1)[0]


@pytest.fixture
def base_url(server):
    return f"http://{server}"


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
        creator.put_readme(README)
        for tag in TAGS:
            creator.put_tag(tag)
        for key, value in ANNOTATIONS.items():
            creator.put_annotation(key, value)
        uri = creator.uri
    return dtoolcore.DataSet.from_uri(uri)


def dtool(env, *args, check=True, **kwargs):
    result = subprocess.run(["dtool", *args], env=env, capture_output=True,
                            text=True, timeout=TIMEOUT, **kwargs)
    if check and result.returncode != 0:
        pytest.fail(f"dtool {' '.join(args)} failed:\n"
                    f"{result.stdout}\n{result.stderr}")
    return result


def claims(token):
    import jwt
    return jwt.decode(token, options={"verify_signature": False})


def config_path(env):
    return os.path.join(env["HOME"], ".config", "dtool", "dtool.json")


def stored_token(env, server):
    with open(config_path(env)) as fh:
        return json.load(fh).get(f"DSERVER_TOKEN_{server}")


def assert_not_logged_in(env, server):
    result = dtool(env, "ls", E2E_BASE_URI, check=False)
    assert result.returncode != 0
    assert f"dtool dserver login {server}" in result.stdout + result.stderr


def browser_login(base_url):
    """Log in through the OAuth2 plugin like a browser; return the token.

    Follows the redirects of /auth/oauth2/login -> provider (the mock logs
    in without a form) -> /auth/oauth2/callback, which redirects to the
    frontend with the token in the URL fragment.
    """
    import requests

    session = requests.Session()
    url = f"{base_url}/auth/oauth2/login"
    for _ in range(10):
        response = session.get(url, allow_redirects=False, timeout=10)
        assert response.status_code in (301, 302, 303, 307), \
            f"{url}: HTTP {response.status_code}\n{response.text}"
        url = urljoin(url, response.headers["Location"])
        match = re.search(r"#token=([^&]+)", url)
        if match:
            return match.group(1)
    pytest.fail(f"Browser login did not deliver a token; last URL {url}")


def device_login(env, server, web_token):
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


def ldap_login(env, server, username, password):
    """Run 'dtool dserver login --method ldap', typing the password."""
    # Without a controlling terminal (new session), the hidden password
    # prompt reads from stdin.
    return dtool(env, "dserver", "login", server, "--method", "ldap",
                 "--username", username, input=password + "\n",
                 check=False, start_new_session=True)


def assert_same_dataset(env, uri, reference_uri):
    """Compare two datasets with the dtool command line."""
    # Identifiers, sizes and (--full) content hashes. dtool diff prints its
    # progress; differences show as "Different ..." and exit codes 1-3.
    result = dtool(env, "diff", "--full", uri, reference_uri, check=False)
    assert result.returncode == 0 and "Different" not in result.stdout, \
        result.stdout + result.stderr
    for command in (["readme", "show"], ["tag", "ls"], ["annotation", "ls"]):
        assert dtool(env, *command, uri).stdout == \
            dtool(env, *command, reference_uri).stdout, command
    assert dtool(env, "uuid", uri).stdout == \
        dtool(env, "uuid", reference_uri).stdout


def copy_round_trip(env, local_dataset, download_dir):
    """Upload and download with dtool cp; compare both copies."""
    remote_uri = dtool(env, "cp", local_dataset.uri,
                       E2E_BASE_URI).stdout.strip().splitlines()[-1]
    assert remote_uri == f"{E2E_BASE_URI}/{local_dataset.uuid}"
    assert remote_uri in dtool(env, "ls", E2E_BASE_URI).stdout
    assert_same_dataset(env, remote_uri, local_dataset.uri)

    download_dir.mkdir()
    downloaded_uri = dtool(env, "cp", remote_uri,
                           str(download_dir)).stdout.strip().splitlines()[-1]
    assert_same_dataset(env, downloaded_uri, local_dataset.uri)
    return remote_uri


# --- tests -------------------------------------------------------------------

def test_oauth2_device_login_copy_refresh_and_logout(
        server, base_url, cli_env, local_dataset, tmp_path):
    import requests

    assert_not_logged_in(cli_env, server)

    # The user logs in to dserver in the browser ...
    web_token = browser_login(base_url)
    web_claims = claims(web_token)
    assert web_claims["sub"] == os.environ["E2E_USERNAME"]
    assert web_claims["aud"] == web_claims["iss"] == "dserver"
    me = requests.get(f"{base_url}/me", timeout=10,
                      headers={"Authorization": f"Bearer {web_token}"})
    assert me.status_code == 200, me.text

    # ... and approves the code of the command-line login there.
    output = device_login(cli_env, server, web_token)
    assert f"Logged in to {server} as {web_claims['sub']}" in output

    # The token is stored per server in the dtool config file, readable
    # only by the user. It is the user's, and its session started with the
    # browser login (no extension beyond the maximum session age).
    token = stored_token(cli_env, server)
    assert claims(token)["sub"] == web_claims["sub"]
    assert claims(token)["auth_time"] == web_claims["auth_time"]
    if sys.platform != "win32":
        assert stat.S_IMODE(os.stat(config_path(cli_env)).st_mode) == 0o600
    result = dtool(cli_env, "dserver", "status")
    assert result.stdout.startswith(f"{server}: {web_claims['sub']}, valid")

    # Tokens expire within an hour (JWT_TOKEN_EXPIRY_HOURS=1 in CI), i.e.
    # within the refresh window: any use refreshes the stored token.
    time.sleep(2)
    dtool(cli_env, "ls", E2E_BASE_URI)
    refreshed = stored_token(cli_env, server)
    assert refreshed != token
    assert claims(refreshed)["exp"] > claims(token)["exp"]
    assert claims(refreshed)["sub"] == claims(token)["sub"]
    assert claims(refreshed)["auth_time"] == claims(token)["auth_time"]

    copy_round_trip(cli_env, local_dataset, tmp_path / "download")

    # After logging out, the token is gone and dserver is out of reach.
    result = dtool(cli_env, "dserver", "logout", server)
    assert f"Logged out of {server}" in result.stdout
    assert stored_token(cli_env, server) is None
    assert_not_logged_in(cli_env, server)


def test_ldap_login_and_copy(server, cli_env, local_dataset, tmp_path):
    username = os.environ["E2E_LDAP_USERNAME"]

    result = ldap_login(cli_env, server, username, "wrong-password")
    assert result.returncode != 0
    assert "Login failed" in result.stdout + result.stderr
    assert_not_logged_in(cli_env, server)

    # First login: dserver does not know the user yet and creates it, with
    # permissions on the test base URI (LDAP_DEFAULT_BASE_URIS).
    result = ldap_login(cli_env, server, username,
                        os.environ["E2E_LDAP_PASSWORD"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"Logged in to {server} as {username}" in result.stdout
    assert claims(stored_token(cli_env, server))["sub"] == username

    copy_round_trip(cli_env, local_dataset, tmp_path / "download")

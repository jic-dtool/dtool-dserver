"""Add the LDAP test user for the end-to-end tests.

Waits for the LDAP server, then creates ``ou=people`` and the user
E2E_LDAP_USERNAME with password E2E_LDAP_PASSWORD below it, i.e. the entry
LDAP_USER_DN_TEMPLATE points to. Uses ldap3, a dependency of
dserver-token-generator-plugin-ldap. Safe to run repeatedly.

Environment: LDAP_URI, LDAP_USER_DN_TEMPLATE, E2E_LDAP_ADMIN_DN,
E2E_LDAP_ADMIN_PASSWORD, E2E_LDAP_USERNAME, E2E_LDAP_PASSWORD.
"""

import os
import time

from ldap3 import Connection, Server
from ldap3.core.exceptions import LDAPException


def connect():
    server = Server(os.environ["LDAP_URI"])
    error = None
    for attempt in range(60):
        try:
            return Connection(server, os.environ["E2E_LDAP_ADMIN_DN"],
                              os.environ["E2E_LDAP_ADMIN_PASSWORD"],
                              auto_bind=True)
        except LDAPException as e:
            error = e
            print(f"Attempt {attempt + 1}: LDAP not ready yet ({e})")
            time.sleep(2)
    raise SystemExit(f"LDAP server did not become ready: {error}")


def add(conn, dn, object_class, attributes):
    if not conn.add(dn, object_class, attributes) and \
            conn.result["description"] != "entryAlreadyExists":
        raise SystemExit(f"Could not add {dn}: {conn.result}")


def main():
    username = os.environ["E2E_LDAP_USERNAME"]
    user_dn = os.environ["LDAP_USER_DN_TEMPLATE"].format(username=username)
    people_dn = user_dn.split(",", 1)[1]

    conn = connect()
    add(conn, people_dn, "organizationalUnit", {"ou": "people"})
    add(conn, user_dn, "inetOrgPerson", {
        "uid": username,
        "cn": "LDAP Test User",
        "sn": "User",
        "mail": f"{username}@example.org",
        "userPassword": os.environ["E2E_LDAP_PASSWORD"],
    })
    conn.unbind()
    print(f"LDAP user {user_dn} ready.")


if __name__ == "__main__":
    main()

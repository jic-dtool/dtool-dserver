"""Prepare a minimal dserver for the end-to-end tests.

Creates the database tables, a user with search and register permissions on
a base URI, and writes a JWT for that user. dserver itself is configured
through environment variables (see .github/workflows/test.yml), which this
script shares with the ``flask run`` that serves the API.

Usage::

    python ci/setup_dserver.py --username testuser --base-uri s3://bucket \\
        --private-key jwt_key --token-file token
"""

import argparse
import datetime
import uuid

import jwt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True)
    parser.add_argument("--base-uri", required=True)
    parser.add_argument("--private-key", required=True,
                        help="RSA private key matching JWT_PUBLIC_KEY_FILE")
    parser.add_argument("--token-file", required=True)
    args = parser.parse_args()

    from dservercore import create_app, sql_db
    from dservercore.utils import (
        register_base_uri,
        register_permissions,
        register_users,
    )

    app = create_app()
    with app.app_context():
        sql_db.create_all()
        register_users([dict(username=args.username)])
        register_base_uri(args.base_uri)
        register_permissions(args.base_uri, {
            "users_with_search_permissions": [args.username],
            "users_with_register_permissions": [args.username],
        })

    now = datetime.datetime.now(datetime.timezone.utc)
    with open(args.private_key) as fh:
        private_key = fh.read()
    token = jwt.encode(
        {
            "sub": args.username,
            # dserver requires audience and issuer "dserver" by default.
            "aud": "dserver",
            "iss": "dserver",
            "iat": now,
            "nbf": now,
            "exp": now + datetime.timedelta(hours=2),
            "jti": str(uuid.uuid4()),
            "type": "access",
            "fresh": True,
        },
        private_key,
        algorithm="RS256",
    )
    with open(args.token_file, "w") as fh:
        fh.write(token)

    print(f"dserver prepared: user {args.username!r} may search and "
          f"register on {args.base_uri}; token written to {args.token_file}")


if __name__ == "__main__":
    main()

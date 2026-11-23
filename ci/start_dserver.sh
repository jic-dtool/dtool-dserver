#!/bin/bash
# Start a minimal dserver for the end-to-end tests in the background.
#
# Expects the dserver configuration in the environment (see
# .github/workflows/test.yml) and E2E_WORK_DIR for keys, token, database and
# log. Writes the JWT for E2E_USERNAME to $E2E_WORK_DIR/token.
set -o errexit -o nounset -o pipefail

mkdir -p "$E2E_WORK_DIR"
openssl genrsa -out "$E2E_WORK_DIR/jwt_key" 2048 2>/dev/null
openssl rsa -in "$E2E_WORK_DIR/jwt_key" -pubout -out "$E2E_WORK_DIR/jwt_key.pub" 2>/dev/null

python "$(dirname "$0")/setup_dserver.py" \
    --username "$E2E_USERNAME" \
    --base-uri "$E2E_BACKEND_BASE_URI" \
    --private-key "$E2E_WORK_DIR/jwt_key" \
    --token-file "$E2E_WORK_DIR/token"

flask run --host 127.0.0.1 --port 5000 > "$E2E_WORK_DIR/dserver.log" 2>&1 &
echo $! > "$E2E_WORK_DIR/dserver.pid"

for attempt in $(seq 1 30); do
    if curl -s -o /dev/null -H "Authorization: Bearer $(cat "$E2E_WORK_DIR/token")" \
            http://127.0.0.1:5000/config/info; then
        echo "dserver is up (pid $(cat "$E2E_WORK_DIR/dserver.pid"))"
        exit 0
    fi
    sleep 1
done
echo "dserver did not start:"
cat "$E2E_WORK_DIR/dserver.log"
exit 1

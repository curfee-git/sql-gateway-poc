#!/usr/bin/env bash
# MIT License
#
# Copyright (c) 2026 Philipp Höllinger
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

# Walks through the scenarios in the README, one request per scenario.
# Requires: curl, jq. Expects the gateway to be reachable at GATEWAY_URL
# (defaults to http://localhost:8080, i.e. the docker-compose setup).

set -euo pipefail

GATEWAY_URL="${GATEWAY_URL:-http://localhost:8080}"

for required in curl jq; do
    if ! command -v "$required" >/dev/null 2>&1; then
        echo "demo.sh needs '$required' on PATH. Install it and retry." >&2
        exit 1
    fi
done

bold()    { printf "\033[1m%s\033[0m\n"    "$*"; }
cyan()    { printf "\033[1;36m%s\033[0m\n" "$*"; }
dim()     { printf "\033[2m%s\033[0m\n"    "$*"; }
section() { printf "\n\033[1;33m== %s\033[0m\n\n" "$*"; }

call_gateway() {
    local title="$1"
    local sql="$2"
    cyan "--- $title"
    dim  "    $sql"
    curl -fsS -X POST "$GATEWAY_URL/query" \
        -H 'Content-Type: application/json' \
        --data-binary "$(jq -n --arg q "$sql" '{query_text: $q}')" \
        | jq -c '{status, reason, error_code, result}'
    echo
}

bold "SQL Gateway demo against $GATEWAY_URL"

section "Scenario set 1: allowed by both layers"

call_gateway "legitimate read" \
    "SELECT id, email, name FROM users WHERE id = 1"

call_gateway "legitimate bounded write" \
    "UPDATE orders SET status = 'shipped' WHERE id = 1"

call_gateway "write with a secret (redacted in the observability log)" \
    "INSERT INTO users (email, name, password_hash) VALUES ('carol@example.com', 'Carol', '\$2b\$12\$realhash')"

section "Scenario set 2: rejected at layer 1 (SQL parser)"

call_gateway "DROP TABLE (root statement not on allowlist)" \
    "DROP TABLE users"

call_gateway "unbounded DELETE (no WHERE clause)" \
    "DELETE FROM orders"

call_gateway "data-modifying CTE hidden inside a SELECT" \
    "WITH d AS (DELETE FROM orders RETURNING *) SELECT * FROM d"

call_gateway "server-side file read" \
    "SELECT pg_read_file('/etc/passwd')"

call_gateway "multi-statement smuggling" \
    "SELECT 1; DROP TABLE users"

section "Scenario set 3: allowed at layer 1, rejected at layer 2 (database permissions)"

call_gateway "read a sensitive column (column-level permission blocks it)" \
    "SELECT id, password_hash FROM users WHERE id = 1"

call_gateway "SELECT * on a table with restricted columns" \
    "SELECT * FROM users WHERE id = 1"

bold "Demo complete."

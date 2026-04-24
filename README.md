<div align="center">

# SQL Gateway

### _Decision Enforcement for AI Agents_

**A rule is only real when the system cannot violate it.**

<br/>

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.136-009485?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Postgres](https://img.shields.io/badge/Postgres-16-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![sqlglot](https://img.shields.io/badge/sqlglot-30.6-8A2BE2)](https://github.com/tobymao/sqlglot)
![CI](https://img.shields.io/badge/CI-ruff%20%7C%20mypy%20%7C%20pytest-111827)
![Tests](https://img.shields.io/badge/tests-114%20unit%20%2B%2016%20integration-2EA44F)
![DI](https://img.shields.io/badge/DI-wireup%20%40injectable-4B6FD6)
![Type Checked](https://img.shields.io/badge/mypy-strict-1F6FEB)
![Architecture](https://img.shields.io/badge/architecture-hexagonal-6F42C1)
![Status](https://img.shields.io/badge/status-proof%20of%20concept-orange)

<sub>A proof of concept that shows what _decision enforcement_ looks like when rules live in the system instead of the prompt. Hexagonal layout, annotation-based DI (`@injectable`), dynamic adapter loading: swap Postgres for another database by setting one environment variable.</sub>

</div>

---

## Table of contents

- [What this is](#what-this-is)
- [Why two layers](#why-two-layers)
- [Architecture](#architecture)
- [Quickstart](#quickstart)
- [Endpoints](#endpoints)
- [Live observability](#live-observability)
- [Demo scenarios](#demo-scenarios)
- [How a request flows](#how-a-request-flows)
- [Validation rules](#validation-rules)
- [Configuration](#configuration)
- [Repository layout](#repository-layout)
- [Adding a database adapter](#adding-a-database-adapter)
- [Tests](#tests)
- [Out of scope](#out-of-scope)
- [License](#license)

---

## What this is

An HTTP gateway that sits between an AI agent and a Postgres database. The
agent sends SQL to `POST /query`; the gateway decides whether to forward it
to the database, forwards it if allowed, and records one observability entry
per request.

"Allowed" is defined by two overlapping checks, each strong where the other
is weak. A rule stated once in one layer can slip through. A rule expressed
in both the parser and the database role cannot.

> [!NOTE]
> This repo is a companion artifact to a LinkedIn post on decision
> enforcement. The code is short on purpose; the design is the part worth
> reading.

---

## Why two layers

Rules like _"the agent must not run destructive queries"_ are only real
when the system cannot execute them. Prompts can be bypassed; code reviews
miss edge cases; individual discipline does not scale. The gateway puts the
rule in two places at once:

- **Layer 1, the SQL parser** (`sqlglot` + six AST rules, inside the
  gateway). Fast, informative, returns HTTP 400 with a machine-readable
  rejection code. Good at structural checks: multi-statement smuggling,
  data-modifying CTEs, blocked server-side functions.
- **Layer 2, the database role** (`agent_rw`, defined in
  [`src/infrastructure/persistence/postgres/init.sql`](src/infrastructure/persistence/postgres/init.sql)).
  Authoritative. Good at things a parser cannot reliably see: which
  columns hold secrets, which functions are revoked, what `SELECT *`
  actually touches.

The two layers are not redundant. They overlap where they can (both block
DDL) and cover each other where they must (Layer 2 catches sensitive-column
reads that Layer 1 cannot identify; Layer 1 catches structural smuggling
and function calls that Layer 2 would let through). That pairing is the
point of the repo.

> [!IMPORTANT]
> The parser and the permissions are the same decision written in two
> languages. The duplication is the feature, not the waste.

---

## Architecture

```text
                         ┌──────────────┐
                         │   AI Agent   │
                         └──────┬───────┘
                                │  POST /query { query_text }
                                ▼
   ┌──────────────────────────────────────────────────────────────┐
   │   LAYER 1  ·  SQL Gateway  ·  this repo                      │
   │                                                              │
   │   ┌─────────┐   ┌─────────┐   ┌──────────┐   ┌────────────┐  │
   │   │ sqlglot │──▶│  6 AST  │──▶│ literal  │──▶│ per-request│  │
   │   │  parse  │   │  rules  │   │redaction │   │ txn + 5s to│  │
   │   └─────────┘   └─────────┘   └──────────┘   └──────┬─────┘  │
   │                                                     │        │
   │   on rule violation  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─▶  HTTP 400    │
   │                                                     │        │
   └─────────────────────────────────────────────────────┼────────┘
                                                         │
                                          allowed SQL    │
                                                         ▼
   ┌──────────────────────────────────────────────────────────────┐
   │   LAYER 2  ·  Postgres  ·  init.sql                          │
   │                                                              │
   │   ┌──────────────┐   ┌──────────────┐   ┌─────────────────┐  │
   │   │ role         │   │ column       │   │ revoked server  │  │
   │   │ agent_rw     │   │ permissions  │   │ functions       │  │
   │   │ no DDL, ever │   │ hash/key off │   │ pg_read_file …  │  │
   │   └──────────────┘   └──────────────┘   └─────────────────┘  │
   │                                                              │
   │   permission denied  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─▶  HTTP 502          │
   │   success            ─ ─ ─ ─ ─ ─ ─ ─ ─ ─▶  HTTP 200 + rows   │
   └──────────────────────────────────────────────────────────────┘
```

Both layers are adapter-specific. The repo ships one concrete adapter
(Postgres) but the architecture is a plugin registry. Swap is one
environment variable plus one adapter package; zero edits to gateway code.
See [Adding a database adapter](#adding-a-database-adapter).

---

## Quickstart

### With Docker

```bash
make compose-up          # build and start postgres + gateway
./demo.sh                # in a second terminal, run the demo scenarios
```

Open `http://localhost:8080/observability` to watch requests appear in real
time. Watch the gateway container logs to see one JSON observability line
per request.

### Without Docker

```bash
make setup               # copies .env.example to .env, installs dev deps
make run                 # starts uvicorn with reload on http://localhost:8080
```

---

## Endpoints

| Method | Path                    | Purpose                                                                                         |
| :----- | :---------------------- | :---------------------------------------------------------------------------------------------- |
| POST   | `/query`                | The agent-facing endpoint. Body: `{"query_text": "..."}`.                                       |
| GET    | `/health`               | Liveness. Always 200 if the process is up.                                                      |
| GET    | `/readiness`            | Opens a short-lived DB connection and runs `SELECT 1`. 503 if the backing store is unreachable. |
| GET    | `/docs`                 | Swagger UI.                                                                                     |
| GET    | `/openapi.json`         | OpenAPI schema.                                                                                 |
| GET    | `/observability`        | Live HTML page, one card per `/query` request, streamed.                                        |
| GET    | `/observability/events` | Server-Sent Events stream the page consumes.                                                    |

`POST /query` returns one of three shapes:

| Decision   | Status | Body                                                                  |
| :--------- | -----: | :-------------------------------------------------------------------- |
| `allowed`  |    200 | `request_id`, `result.{columns, rows, rows_affected, truncated}`      |
| `rejected` |    400 | `request_id`, `reason` (rejection code), `message`, optional `detail` |
| `db_error` |    502 | `request_id`, `reason` (sanitized message), `error_code` (SQLSTATE)   |

The docker-compose healthcheck targets `/readiness`, so the service is only
reported healthy when it can actually serve queries.

---

## Live observability

Open `http://localhost:8080/observability` once the gateway is up. Every
`/query` request appears as a card. Title and description are derived from
the query text and the gateway's decision. The page is populated by the
gateway itself via Server-Sent Events; nothing is hardcoded.

### Three sinks, two payloads

Every request is recorded by a `MultiSinkObservabilityRecorderAdapter`,
which fans each entry out to three downstream recorders. A failure in one
sink is logged and the remaining sinks still receive the entry.

| Recorder                                | Payload            | Purpose                                                                      |
| :-------------------------------------- | :----------------- | :--------------------------------------------------------------------------- |
| `StdoutObservabilityRecorderAdapter`    | PII-free JSON line | Container logs, audit trail. Drops `rows` and `columns`.                     |
| `JsonlFileObservabilityRecorderAdapter` | PII-free JSON line | Optional append-only file. Active only if `OBSERVABILITY_JSONL_PATH` is set. |
| `InMemoryObservabilityRecorderAdapter`  | Full payload       | Backs the `/observability` page. Ring buffer, last 500 entries.              |

The split is deliberate. Stdout and the JSONL file carry the same PII-free
view: decision, redacted query, rejection code, SQLSTATE, timings, and
counts. The in-memory buffer keeps the full payload (including `rows` and
`columns`) so the live page can render the same detail a developer would
want when watching the demo. Row data never reaches stdout, never reaches
disk, and lives only as long as the gateway process. In production you
would drop the in-memory buffer or replace it with a sink that redacts
values per your policy.

### How the SSE stream works

- The page opens `GET /observability/events`.
- On connect, the controller replays the current ring-buffer snapshot, then
  streams new entries as they arrive.
- Each subscriber has its own bounded `asyncio.Queue` (cap 1000). A slow
  consumer drops entries for itself and logs a throttled warning; other
  subscribers are unaffected.
- Disconnects are detected via `request.is_disconnected()` and the
  subscriber is removed.
- Heartbeats (`: keepalive`) are sent every 15 seconds so proxies don't
  close idle connections.
- The client also caps its DOM at 500 cards and dedupes by `request_id`
  across reconnects.

---

## Demo scenarios

[`demo.sh`](demo.sh) walks through ten scenarios. The **Blocked by**
column is the decision enforcement point.

|   # | Scenario                   | SQL                                                | Blocked by                             |
| --: | :------------------------- | :------------------------------------------------- | :------------------------------------- |
|   1 | Legitimate read            | `SELECT id, email, name FROM users WHERE id = 1`   | Allowed, HTTP 200                      |
|   2 | Schema destruction         | `DROP TABLE users`                                 | Gateway: `root_not_allowed`            |
|   3 | Unbounded delete           | `DELETE FROM orders`                               | Gateway: `unbounded_write`             |
|   4 | Data-modifying CTE         | `WITH d AS (DELETE FROM orders ...) SELECT ...`    | Gateway: `data_modifying_cte`          |
|   5 | Server-side file read      | `SELECT pg_read_file('/etc/passwd')`               | Gateway: `dangerous_function`          |
|   6 | Multi-statement smuggling  | `SELECT 1; DROP TABLE users`                       | Gateway: `multi_statement`             |
|   7 | Reading a sensitive column | `SELECT id, password_hash FROM users ...`          | DB role: column-level permission       |
|   8 | Implicit sensitive column  | `SELECT * FROM users ...`                          | DB role: column-level permission       |
|   9 | Legitimate bounded write   | `UPDATE orders SET status = 'shipped' WHERE ...`   | Allowed, redacted in observability log |
|  10 | Write with a secret        | `INSERT INTO users (... password_hash) VALUES ...` | Allowed, secret marked `[REDACTED]`    |

> [!TIP]
> Rows 7 and 8 are the interesting ones. A parser cannot reliably tell
> which columns are sensitive: naming varies, schemas change, new columns
> arrive. The database is the right place for that decision to live.

---

## How a request flows

```text
   Agent ──▶ FastAPI Router                       POST /query { query_text }
                │
                ├─▶ QueryScrubber.scrub(sql)      runs FIRST so even rejected
                │◀─ redacted_sql                  queries land in the log with
                │                                 literals scrubbed
                ├─▶ QueryValidator.validate(sql)
                │◀─ ValidationResultDto
                │
                ├── if rejected ──────────────────────────────────────────────────────┐
                │   ├─▶ ObservabilityRecorder.record(decision=rejected, reason)       │
                │   └─▶ Agent                      HTTP 400 { reason, message }       │
                │                                                                     │
                └── if allowed                                                        │
                    │                                                                 │
                    ├─▶ QueryExecutor.execute(sql)                                    │
                    │      │                                                          │
                    │      ├─▶ Postgres             BEGIN                             │
                    │      │                        SET LOCAL statement_timeout       │
                    │      │                        <agent's SQL>                     │
                    │      │                        COMMIT                            │
                    │      │                                                          │
                    │      ├── DB denies or times out ──────────────────────────────┐ │
                    │      │   └─▶ QueryOutcomeDto(succeeded=False, sqlstate, …)    │ │
                    │      │                                                        │ │
                    │      └── DB runs it                                           │ │
                    │          └─▶ QueryOutcomeDto(succeeded=True, rows, columns)   │ │
                    │                                                               │ │
                    ├── if db_error ────────────────────────────────────────────────┤ │
                    │   ├─▶ ObservabilityRecorder.record(decision=db_error)         │ │
                    │   └─▶ Agent                 HTTP 502 { reason, error_code }   │ │
                    │                                                               │ │
                    └── if success                                                  │ │
                        ├─▶ ObservabilityRecorder.record(allowed, rows, duration)   │ │
                        └─▶ Agent                 HTTP 200 { result }               │ │
                                                                                    │ │
   ◀────────────── one observability entry is recorded on every path ───────────────┘ ┘
```

---

## Validation rules

Each rule is a single class with one method: `check(statement) -> ValidationResultDto`.
`QueryValidator` parses once and fans the AST out to every rule.

|  # | Rule                         | Rejection code       | Rejects                                                           |
| -: | :--------------------------- | :------------------- | :---------------------------------------------------------------- |
|  1 | `AllowedRootStatementRule`   | `root_not_allowed`   | Anything that is not `SELECT` / `INSERT` / `UPDATE` / `DELETE`    |
|  2 | `NoForbiddenConstructsRule`  | `forbidden_construct`| DDL and transaction-control anywhere in the tree                  |
|  3 | `NoSelectIntoRule`           | `select_into`        | `SELECT ... INTO new_table` (a disguised `CREATE TABLE`)          |
|  4 | `NoDataModifyingCteRule`     | `data_modifying_cte` | `WITH x AS (DELETE ...) SELECT ...` and friends                   |
|  5 | `NoDangerousFunctionsRule`   | `dangerous_function` | `pg_read_file`, `dblink_exec`, `lo_export`, etc.                  |
|  6 | `BoundedWriteRule`           | `unbounded_write`    | `UPDATE` / `DELETE` without a `WHERE`                             |

Three pre-rule checks inside the validator cover the rest: `empty_query`,
`parse_error`, `multi_statement`.

Adding a rule is one decorated class. Drop a file under
`src/infrastructure/persistence/postgres/rules/`, decorate it with
`@sql_rule(dialects=["postgres"])`, and the validator picks it up at
startup. The registry lives in
[`src/infrastructure/persistence/sql/rule_registry.py`](src/infrastructure/persistence/sql/rule_registry.py).

---

## Configuration

[`.env.example`](.env.example) is the template. Settings are loaded by
`GatewaySettings` in
[`src/infrastructure/config/settings.py`](src/infrastructure/config/settings.py);
the gateway refuses to boot if required variables are missing.

| Variable                           | Required | Default | Description                                                                                                               |
| :--------------------------------- | :------: | :------ | :------------------------------------------------------------------------------------------------------------------------ |
| `DATABASE_ADAPTER`                 |   yes    | n/a     | Name of the adapter package under `src/infrastructure/persistence/`. Ships with `postgres`.                               |
| `DATABASE_URL`                     |   yes    | n/a     | Connection string understood by the selected adapter.                                                                     |
| `QUERY_TIMEOUT_MS`                 |    no    | `5000`  | Upper bound on how long one query may run.                                                                                |
| `MAX_RESULTS`                      |    no    | `1000`  | Upper bound on records returned by one read.                                                                              |
| `MAX_SAMPLE_ROWS_IN_OBSERVABILITY` |    no    | `20`    | Rows kept per allowed-query entry in the in-memory buffer. Column names are always kept. The HTTP response is unaffected. |
| `OBSERVABILITY_JSONL_PATH`         |    no    | `""`    | Absolute path of a PII-free JSONL file to append to. Empty disables the file sink.                                        |

---

## Repository layout

```text
sql_gateway_poc/
├─ src/                                Namespace packages only. No __init__.py.
│  ├─ main.py                          Composition root. Loads the selected adapter,
│  │                                   walks every package so the Wireup container
│  │                                   sees each @injectable, and mounts every
│  │                                   controller router.
│  │
│  ├─ core/                            Pure domain. No FastAPI, no psycopg.
│  │  ├─ ports/
│  │  │  ├─ inbound/
│  │  │  │  ├─ execute_query_port.py
│  │  │  │  ├─ execute_query_result_dto.py
│  │  │  │  ├─ check_readiness_port.py
│  │  │  │  └─ readiness_report_dto.py
│  │  │  └─ outbound/
│  │  │     ├─ query_executor.py
│  │  │     ├─ query_outcome_dto.py
│  │  │     ├─ query_validator.py
│  │  │     ├─ validation_result_dto.py
│  │  │     ├─ query_scrubber.py
│  │  │     ├─ observability_recorder.py
│  │  │     └─ observability_entry_dto.py
│  │  └─ model/
│  │     ├─ access_guard.py            The triple that mediates agent <-> store.
│  │     ├─ decision_enum.py           DecisionEnum: ALLOWED / REJECTED / DB_ERROR.
│  │     └─ query_payload.py           str | dict | list. Adapter decides.
│  │
│  ├─ application/
│  │  ├─ use_cases/
│  │  │  ├─ execute_query_use_case.py
│  │  │  └─ check_readiness_use_case.py
│  │  └─ controllers/http/
│  │     ├─ gateway/
│  │     │  ├─ gateway_http_controller.py           POST /query.
│  │     │  ├─ query_request.py
│  │     │  ├─ query_result_payload.py
│  │     │  ├─ query_allowed_response.py
│  │     │  ├─ query_rejected_response.py
│  │     │  └─ query_database_error_response.py
│  │     ├─ probes/
│  │     │  ├─ probes_http_controller.py            GET /health + GET /readiness.
│  │     │  ├─ health_response.py                   HealthEnum + body.
│  │     │  └─ readiness_response.py                ReadinessEnum + DatabaseStatusEnum.
│  │     └─ observability/
│  │        └─ observability_http_controller.py     GET /observability + SSE stream.
│  │
│  └─ infrastructure/
│     ├─ config/
│     │  └─ settings.py                             GatewaySettings + Wireup factory.
│     ├─ observability/
│     │  ├─ stdout_observability_recorder_adapter.py       PII-free JSON line per entry.
│     │  ├─ jsonl_file_observability_recorder_adapter.py   PII-free append-only file.
│     │  ├─ in_memory_observability_recorder_adapter.py    Ring buffer + SSE fan-out.
│     │  └─ multi_sink_observability_recorder_adapter.py   Fans out to all three sinks.
│     └─ persistence/
│        ├─ sql/                                    Shared across SQL-family adapters.
│        │  ├─ query_validator.py                   Base class for dialect validators.
│        │  ├─ query_scrubber_adapter.py            QueryScrubber port implementation.
│        │  └─ rule_registry.py                     @sql_rule + rules_for(dialect).
│        └─ postgres/
│           ├─ query_executor_adapter.py
│           ├─ query_validator_adapter.py
│           ├─ query_scrubber_adapter.py
│           ├─ rules/                               One decorated class per rule.
│           └─ init.sql                             Layer 2: role, grants, revokes.
│
├─ tests/                              Mirrors src/ one-to-one.
│  ├─ conftest.py
│  ├─ test_main_smoke.py               Wireup end-to-end + adapter swap.
│  ├─ application/...
│  ├─ core/...
│  ├─ infrastructure/...
│  └─ integration/                     Opt-in, needs Docker.
│     └─ test_db_permissions.py
│
├─ Dockerfile
├─ docker-compose.yml                  Postgres + gateway, with healthchecks.
├─ demo.sh
├─ .env.example
├─ Makefile
├─ pyproject.toml
├─ .github/workflows/ci.yml
├─ LICENSE
└─ README.md
```

### One controller per audience

The REST surface has three distinct audiences. Each has its own controller
class, its own `APIRouter`, and its own sub-package.

| Controller                         | Endpoints                                         | Audience                                   |
| :--------------------------------- | :------------------------------------------------ | :----------------------------------------- |
| `gateway_http_controller.py`       | `POST /query`                                     | Agents                                     |
| `probes_http_controller.py`        | `GET /health`, `GET /readiness`                   | Orchestrators (Kubernetes, load balancers) |
| `observability_http_controller.py` | `GET /observability`, `GET /observability/events` | Humans watching the live page              |

`main.py` walks `application/controllers/` at startup, discovers every
`@injectable` class with a `router` attribute, and mounts each one. Adding
a controller is dropping a new class in a new sub-package; `main.py`
does not change.

---

## Adding a database adapter

The plugin point is one environment variable. `DATABASE_ADAPTER=<name>`
tells `main.py` to import `src/infrastructure/persistence/<name>/` and walk
it for `@injectable` decorators. No registry file to edit, no switch
statement to update. Each adapter package is self-contained and provides
one concrete class per outbound port: `QueryExecutor`, `QueryValidator`,
`QueryScrubber`.

### MySQL (SQL-family, reuses base classes)

1. Create `src/infrastructure/persistence/mysql/` with:
   - `query_executor_adapter.py`: `MysqlQueryExecutorAdapter` targeting `QueryExecutor`.
   - `query_validator_adapter.py`: `MysqlQueryValidatorAdapter(SqlQueryValidator)` with `_dialect = "mysql"`.
   - `query_scrubber_adapter.py`: `MysqlQueryScrubberAdapter(SqlQueryScrubberAdapter)`. Sqlglot handles the dialect.
   - `rules/`: MySQL-specific rules, each decorated with `@sql_rule(dialects=["mysql"])`.
2. Set `DATABASE_ADAPTER=mysql DATABASE_URL=mysql://...` at boot.

### Mongo (NoSQL, standalone)

1. Create `src/infrastructure/persistence/mongo/` with:
   - `query_executor_adapter.py`: `MongoQueryExecutorAdapter` using `pymongo`. Parses the `query_text` JSON (`{"op": "find", "collection": "users", "filter": {...}}`).
   - `query_validator_adapter.py`: written from scratch (no SQL base). Rejects `$where`, `$eval`, `deleteMany` without a filter, etc.
   - `query_scrubber_adapter.py`: walks the JSON doc and masks values on sensitive keys.
2. Set `DATABASE_ADAPTER=mongo DATABASE_URL=mongodb://...` at boot.

No shared plumbing is pulled in for Mongo; the walker only touches
`mongo/`. The same shape works for DynamoDB, Redis, RavenDB, or anything
else: self-contained folder, three classes, done.

---

## Tests

```bash
make test                # unit tests, no DB required
make test-integration    # integration tests, need Docker
make gate                # lint + mypy + unit tests in one shot
```

114 unit tests run against fake collaborators. 16 integration tests exercise
the real `init.sql` against a fresh Postgres 16 container via
`testcontainers` and prove Layer 2 empirically. Integration tests are
marked `@pytest.mark.integration` and skipped by default; they also skip
gracefully if the Docker daemon is not reachable.

<details>
<summary><b>What the 114 unit tests cover</b></summary>

| Area                              |   Count | File                                                                                       |
| :-------------------------------- | ------: | :----------------------------------------------------------------------------------------- |
| SQL rules + validator             |      58 | `tests/infrastructure/persistence/postgres/test_query_validator_adapter.py`                |
| Redaction                         |      21 | `tests/infrastructure/persistence/sql/test_query_scrubber_adapter.py`                      |
| Execute-query use case            |       6 | `tests/application/use_cases/test_execute_query.py`                                        |
| Smoke / adapter swap              |       5 | `tests/test_main_smoke.py`                                                                 |
| Gateway controller                |       4 | `tests/application/controllers/http/gateway/test_controller.py`                            |
| Observability entry DTO           |       4 | `tests/core/ports/outbound/test_observability_entry_dto.py`                                |
| In-memory observability recorder  |       4 | `tests/infrastructure/observability/test_in_memory_observability_recorder_adapter.py`      |
| Probes controller                 |       3 | `tests/application/controllers/http/probes/test_controller.py`                             |
| Multi-sink observability recorder |       3 | `tests/infrastructure/observability/test_multi_sink_observability_recorder_adapter.py`     |
| Stdout observability recorder     |       2 | `tests/infrastructure/observability/test_stdout_observability_recorder_adapter.py`         |
| JSONL-file observability recorder |       2 | `tests/infrastructure/observability/test_jsonl_file_observability_recorder_adapter.py`     |
| Observability controller          |       2 | `tests/application/controllers/http/observability/test_controller.py`                      |
| **Total**                         | **114** |                                                                                            |

Every test runs against fake collaborators. No database required to
exercise the full HTTP request path.

</details>

<details>
<summary><b>What the 16 integration tests cover (real Postgres via testcontainers)</b></summary>

These prove Layer 2 empirically: they run `init.sql` against a fresh
Postgres 16 container and then connect as `agent_rw` to verify the
permissions do what the schema claims.

| Area                     |  Count | What is verified                                                 |
| :----------------------- | -----: | :--------------------------------------------------------------- |
| Column-level permissions |      4 | `password_hash`, `api_key`, `SELECT *`, and allowed columns      |
| Role cannot alter DDL    |      4 | `DROP`, `ALTER`, `CREATE`, `TRUNCATE` rejected by Postgres       |
| Functions are revoked    |      1 | `pg_read_file` is not executable                                 |
| Reserved-word columns    |      5 | `user`, `group`, `order`, `type`, `analyse` remain readable      |
| Bounded writes           |      2 | Users INSERT+UPDATE works; orders INSERT+UPDATE+DELETE roundtrip |
| **Total**                | **16** |                                                                  |

</details>

---

## Out of scope

This is a proof of concept. For production, add:

- [ ] **Gateway authentication.** Anything reaching `/query` can run allowlisted SQL; a real deployment needs per-agent credentials.
- [ ] **Connection pooling.** PgBouncer between gateway and Postgres.
- [ ] **Structured observability backend.** Stdout and a JSONL file are fine for a demo. The `ObservabilityRecorder` protocol makes swapping in OpenTelemetry, an SIEM, or a log aggregator a one-class change.
- [ ] **Rate limiting and per-agent quotas.**
- [ ] **Multi-step transactions.** This PoC is transaction-per-request only. A session-token mode (client calls `BEGIN` / `COMMIT` explicitly) is the next step if the agent needs to read intermediate results before deciding what to write.
- [ ] **Read-replica routing.** `SELECT`s to a replica, writes to the primary. The parser already knows which is which.

### Why not a wire-protocol proxy?

For a production version, a wire-protocol proxy in the shape of pgcat is a
better base. You get transparent transactions, prepared statements, real
tooling support (psql, pgAdmin, any ORM), connection pooling, row
streaming, and type fidelity without any JSON transcoding in the middle.

This repo goes REST on purpose. The point it wants to make is that rules
belong in the system instead of the prompt, and that is easier to show
with curl, docker-compose, and a live HTML page than with a proxy a
reader has to install and point libpq at.

The design does not depend on the surface. The real parts are the
validation rule registry and the database role. Put a pgcat-shaped proxy
in front of the same rules and the same role, and the enforcement still
holds. Same idea, different entry point.

---

## License

Released under the [MIT License](LICENSE). Copyright &copy; 2026 Philipp Höllinger.

<div align="center">
<br/>
<sub>Built as a companion to a post on the <b>Decision Enforcement Principle</b>. <br/> If you enjoyed the design, the principle is worth more than the code.</sub>
</div>

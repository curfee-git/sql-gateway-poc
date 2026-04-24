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

"""Postgres QueryExecutor adapter: runs each query in its own transaction."""

from __future__ import annotations

import re
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg
from wireup import injectable

from core.model.query_payload import QueryPayload
from core.ports.outbound.query_executor import QueryExecutor
from core.ports.outbound.query_outcome_dto import QueryOutcomeDto
from infrastructure.config.settings import GatewaySettings

_CONSTRAINT_VALUE_LEAK_PATTERN = re.compile(r"=\([^)]*\)")
_INLINE_QUOTED_LITERAL_PATTERN = re.compile(r"""(['"])(?:\\.|(?!\1).)*\1""")
_MAX_ERROR_MESSAGE_LENGTH = 200
_PING_CONNECT_TIMEOUT_SECONDS = 2


@injectable(as_type=QueryExecutor)
class PostgresQueryExecutorAdapter:
    """Runs each statement in its own transaction with a statement timeout."""

    def __init__(self, settings: GatewaySettings) -> None:
        self._database_url = settings.database_url
        self._query_timeout_ms = settings.query_timeout_ms
        self._max_results = settings.max_results

    def execute(self, query_text: QueryPayload) -> QueryOutcomeDto:
        if not isinstance(query_text, str):
            return QueryOutcomeDto(
                succeeded=False,
                error_message=(
                    f"Postgres executor expects a string, "
                    f"got {type(query_text).__name__}"
                ),
            )
        try:
            with (
                psycopg.connect(self._database_url, autocommit=False) as connection,
                connection.cursor() as cursor,
            ):
                cursor.execute(
                    "SELECT set_config('statement_timeout', %s, true)",
                    (f"{self._query_timeout_ms}ms",),
                )
                cursor.execute(query_text)

                if cursor.description is not None:
                    outcome = self._build_read_outcome(cursor)
                else:
                    outcome = QueryOutcomeDto(
                        succeeded=True, rows_affected=cursor.rowcount
                    )

                connection.commit()
                return outcome
        except psycopg.Error as exception:
            return self._build_error_outcome(exception)

    def ping(self) -> bool:
        try:
            with (
                psycopg.connect(
                    self._database_url,
                    connect_timeout=_PING_CONNECT_TIMEOUT_SECONDS,
                ) as connection,
                connection.cursor() as cursor,
            ):
                cursor.execute("SELECT 1")
                return cursor.fetchone() == (1,)
        except psycopg.Error:
            return False

    def _build_read_outcome(self, cursor: psycopg.Cursor) -> QueryOutcomeDto:
        assert cursor.description is not None
        fetched_rows = cursor.fetchmany(self._max_results + 1)
        rows_were_truncated = len(fetched_rows) > self._max_results
        visible_rows = fetched_rows[: self._max_results]
        column_names = [description.name for description in cursor.description]
        return QueryOutcomeDto(
            succeeded=True,
            columns=column_names,
            rows=[
                [_coerce_cell_to_json_safe(cell) for cell in row]
                for row in visible_rows
            ],
            rows_were_truncated=rows_were_truncated,
        )

    @staticmethod
    def _build_error_outcome(exception: psycopg.Error) -> QueryOutcomeDto:
        sqlstate: str | None = None
        primary_message: str | None = None
        if hasattr(exception, "diag") and exception.diag is not None:
            sqlstate = getattr(exception.diag, "sqlstate", None)
            primary_message = getattr(exception.diag, "message_primary", None)

        if primary_message:
            raw_message = primary_message
        else:
            full_text = str(exception)
            raw_message = full_text.splitlines()[0] if full_text else ""
        return QueryOutcomeDto(
            succeeded=False,
            error_message=_sanitize_error_message(raw_message),
            error_code=sqlstate,
        )


def _coerce_cell_to_json_safe(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bytes | bytearray | memoryview):
        return bytes(value).hex()
    return str(value)


def _sanitize_error_message(message: str) -> str:
    if not message:
        return ""
    cleaned = _CONSTRAINT_VALUE_LEAK_PATTERN.sub("=(…)", message)
    cleaned = _INLINE_QUOTED_LITERAL_PATTERN.sub("'…'", cleaned)
    cleaned = cleaned.strip()
    return cleaned[:_MAX_ERROR_MESSAGE_LENGTH]

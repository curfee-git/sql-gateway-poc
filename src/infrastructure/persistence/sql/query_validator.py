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

"""SQL validator base class shared across SQL-family adapters."""

from __future__ import annotations

from typing import Literal

from sqlglot import exp, parse
from sqlglot.errors import SqlglotError

from core.model.query_payload import QueryPayload
from core.ports.outbound.validation_result_dto import ValidationResultDto
from infrastructure.persistence.sql.rule_registry import (
    SqlValidationRule,
    rules_for,
)

SqlRejectionCode = Literal[
    "empty_query",
    "parse_error",
    "multi_statement",
    "root_not_allowed",
    "forbidden_construct",
    "select_into",
    "data_modifying_cte",
    "unbounded_write",
    "dangerous_function",
    "payload_type_mismatch",
]

_MAX_REJECTION_DETAIL_LENGTH = 120


class SqlQueryValidator:
    """Parses SQL once and evaluates each registered rule against the AST."""

    _dialect: str = ""

    @property
    def _rules(self) -> tuple[SqlValidationRule, ...]:
        return rules_for(self._dialect)

    def validate(self, query_text: QueryPayload) -> ValidationResultDto:
        if not isinstance(query_text, str):
            return ValidationResultDto.reject(
                "payload_type_mismatch",
                f"SQL adapter expects a string, got {type(query_text).__name__}",
            )
        if not query_text or not query_text.strip():
            return ValidationResultDto.reject("empty_query")

        try:
            parsed_statements = parse(query_text, dialect=self._dialect)
        except SqlglotError as exception:
            return ValidationResultDto.reject(
                "parse_error", _compact_first_line(str(exception))
            )

        non_null_statements = [
            statement for statement in parsed_statements if statement is not None
        ]
        if len(non_null_statements) == 0:
            return ValidationResultDto.reject("empty_query")
        if len(non_null_statements) > 1:
            return ValidationResultDto.reject("multi_statement")

        root_statement: exp.Expression = non_null_statements[0]  # type: ignore[assignment]
        for rule in self._rules:
            rule_result = rule.check(root_statement)
            if not rule_result.is_allowed:
                return rule_result

        return ValidationResultDto.allow()


def _compact_first_line(message: str, limit: int = _MAX_REJECTION_DETAIL_LENGTH) -> str:
    first_line = message.splitlines()[0] if message else ""
    whitespace_collapsed = " ".join(first_line.split())
    if len(whitespace_collapsed) <= limit:
        return whitespace_collapsed
    return whitespace_collapsed[: limit - 1] + "…"

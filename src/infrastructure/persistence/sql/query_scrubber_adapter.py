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

"""SQL QueryScrubber base class shared across SQL-family adapters."""

from __future__ import annotations

import re

from sqlglot import exp, parse_one
from sqlglot.errors import SqlglotError

from core.model.query_payload import QueryPayload

DEFAULT_DIALECT = "postgres"

DEFAULT_SENSITIVE_COLUMN_PATTERN = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|private[_-]?key|"
    r"auth|session|credential|hash|salt|pin|cvv|ssn)",
    re.IGNORECASE,
)

REDACTION_MARKER_TEMPLATE = "[REDACTED:${index}]"
UNPARSEABLE_MARKER = "<unparseable>"


class SqlQueryScrubberAdapter:
    """Replaces every literal in a parsed SQL statement."""

    _sensitive_column_pattern = DEFAULT_SENSITIVE_COLUMN_PATTERN
    _dialect = DEFAULT_DIALECT

    def scrub(self, query_text: QueryPayload) -> str:
        if not isinstance(query_text, str):
            return UNPARSEABLE_MARKER
        try:
            parsed_statement: exp.Expression | None = parse_one(  # type: ignore[assignment]
                query_text, dialect=self._dialect
            )
        except SqlglotError:
            return UNPARSEABLE_MARKER
        if parsed_statement is None:
            return UNPARSEABLE_MARKER

        sensitive_literal_ids = self._collect_sensitive_literal_ids(parsed_statement)
        self._replace_all_literals(parsed_statement, sensitive_literal_ids)

        try:
            return parsed_statement.sql(dialect=self._dialect)
        except Exception:  # pragma: no cover
            return UNPARSEABLE_MARKER

    def _collect_sensitive_literal_ids(self, statement: exp.Expression) -> set[int]:
        sensitive_literal_ids: set[int] = set()
        self._mark_update_set_assignments(statement, sensitive_literal_ids)
        self._mark_insert_values(statement, sensitive_literal_ids)
        return sensitive_literal_ids

    def _mark_update_set_assignments(
        self,
        statement: exp.Expression,
        sensitive_literal_ids: set[int],
    ) -> None:
        for equality in statement.find_all(exp.EQ):
            if not isinstance(equality.parent, exp.Update):
                continue
            if equality.arg_key != "expressions":
                continue
            assignment_target = equality.left
            assigned_value = equality.right

            if isinstance(
                assignment_target, exp.Column
            ) and self._is_sensitive_column_name(assignment_target.name):
                self._mark_all_literals_in(
                    assigned_value,  # type: ignore[arg-type]
                    sensitive_literal_ids,
                )
                continue

            if isinstance(assignment_target, exp.Tuple):
                column_list = assignment_target.expressions
                value_list = (
                    assigned_value.expressions
                    if isinstance(assigned_value, exp.Tuple)
                    else []
                )
                for column_index, column in enumerate(column_list):
                    column_name = getattr(column, "name", "")
                    if not self._is_sensitive_column_name(column_name):
                        continue
                    if column_index < len(value_list):
                        self._mark_all_literals_in(
                            value_list[column_index], sensitive_literal_ids
                        )

    def _mark_insert_values(
        self,
        statement: exp.Expression,
        sensitive_literal_ids: set[int],
    ) -> None:
        for insert_node in statement.find_all(exp.Insert):
            target_schema = insert_node.this
            if not isinstance(target_schema, exp.Schema):
                continue
            target_column_names = [
                getattr(column, "name", "") for column in target_schema.expressions
            ]
            sensitive_column_indexes = {
                index
                for index, column_name in enumerate(target_column_names)
                if self._is_sensitive_column_name(column_name)
            }
            if not sensitive_column_indexes:
                continue

            value_source = insert_node.expression
            if isinstance(value_source, exp.Values):
                self._mark_values_clause(
                    value_source,
                    sensitive_column_indexes,
                    sensitive_literal_ids,
                )
            elif isinstance(value_source, exp.Select):
                self._mark_select_projections(
                    value_source,
                    sensitive_column_indexes,
                    sensitive_literal_ids,
                )

    def _mark_values_clause(
        self,
        values_clause: exp.Values,
        sensitive_column_indexes: set[int],
        sensitive_literal_ids: set[int],
    ) -> None:
        for value_tuple in values_clause.expressions:
            if not isinstance(value_tuple, exp.Tuple):
                continue
            for column_index, value in enumerate(value_tuple.expressions):
                if column_index in sensitive_column_indexes:
                    self._mark_all_literals_in(value, sensitive_literal_ids)

    def _mark_select_projections(
        self,
        select_node: exp.Select,
        sensitive_column_indexes: set[int],
        sensitive_literal_ids: set[int],
    ) -> None:
        projections = select_node.expressions or []
        for column_index, projection in enumerate(projections):
            if column_index in sensitive_column_indexes:
                self._mark_all_literals_in(projection, sensitive_literal_ids)

    @staticmethod
    def _mark_all_literals_in(
        node: exp.Expression,
        sensitive_literal_ids: set[int],
    ) -> None:
        if isinstance(node, exp.Literal):
            sensitive_literal_ids.add(id(node))
            return
        for literal in node.find_all(exp.Literal):
            sensitive_literal_ids.add(id(literal))

    def _is_sensitive_column_name(self, column_name: str | None) -> bool:
        if not column_name:
            return False
        return bool(self._sensitive_column_pattern.search(column_name))

    @staticmethod
    def _replace_all_literals(
        statement: exp.Expression,
        sensitive_literal_ids: set[int],
    ) -> None:
        literals_in_statement = list(statement.find_all(exp.Literal))
        for placeholder_index, literal in enumerate(literals_in_statement, start=1):
            replacement: exp.Expression
            if id(literal) in sensitive_literal_ids:
                replacement = exp.Literal.string(
                    REDACTION_MARKER_TEMPLATE.format(index=placeholder_index)
                )
            else:
                replacement = exp.Placeholder(this=str(placeholder_index))
            literal.replace(replacement)

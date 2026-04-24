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

"""Tests for PostgresQueryValidatorAdapter and every rule it uses."""

from __future__ import annotations

import pytest
from sqlglot import parse_one

from core.ports.outbound.validation_result_dto import ValidationResultDto
from infrastructure.persistence.postgres.query_validator_adapter import (
    PostgresQueryValidatorAdapter,
)
from infrastructure.persistence.postgres.rules.allowed_root_statement_rule import (
    AllowedRootStatementRule,
)
from infrastructure.persistence.postgres.rules.bounded_write_rule import (
    BoundedWriteRule,
)
from infrastructure.persistence.postgres.rules.no_dangerous_functions_rule import (
    NoDangerousFunctionsRule,
)
from infrastructure.persistence.postgres.rules.no_data_modifying_cte_rule import (
    NoDataModifyingCteRule,
)
from infrastructure.persistence.postgres.rules.no_forbidden_constructs_rule import (
    NoForbiddenConstructsRule,
)
from infrastructure.persistence.postgres.rules.no_select_into_rule import (
    NoSelectIntoRule,
)


def _parse(sql: str):
    return parse_one(sql, dialect="postgres")


class TestAllowedRootStatementRule:
    rule = AllowedRootStatementRule()

    @pytest.mark.parametrize(
        "sql",
        [
            "SELECT 1",
            "INSERT INTO t (a) VALUES (1)",
            "UPDATE t SET a = 1 WHERE id = 1",
            "DELETE FROM t WHERE id = 1",
        ],
    )
    def test_accepts_read_and_write_dml(self, sql: str):
        assert self.rule.check(_parse(sql)).is_allowed

    @pytest.mark.parametrize(
        "sql, expected_name",
        [
            ("DROP TABLE t", "Drop"),
            ("ALTER TABLE t ADD COLUMN x INT", "Alter"),
            ("CREATE TABLE t (id INT)", "Create"),
            ("TRUNCATE t", "TruncateTable"),
        ],
    )
    def test_rejects_ddl_at_root(self, sql: str, expected_name: str):
        result = self.rule.check(_parse(sql))
        assert not result.is_allowed
        assert result.rejection_code == "root_not_allowed"
        assert result.rejection_detail == expected_name


class TestNoForbiddenConstructsRule:
    rule = NoForbiddenConstructsRule()

    def test_plain_select_passes(self):
        assert self.rule.check(_parse("SELECT id FROM t")).is_allowed

    @pytest.mark.parametrize(
        "sql",
        [
            "DROP TABLE t",
            "ALTER TABLE t ADD COLUMN x INT",
            "CREATE TABLE t (id INT)",
            "TRUNCATE t",
        ],
    )
    def test_rejects_forbidden_constructs(self, sql: str):
        result = self.rule.check(_parse(sql))
        assert not result.is_allowed
        assert result.rejection_code == "forbidden_construct"


class TestNoSelectIntoRule:
    rule = NoSelectIntoRule()

    def test_plain_select_passes(self):
        assert self.rule.check(_parse("SELECT id FROM t WHERE id = 1")).is_allowed

    def test_non_select_passes(self):
        assert self.rule.check(_parse("INSERT INTO t (a) VALUES (1)")).is_allowed

    def test_rejects_select_into(self):
        result = self.rule.check(_parse("SELECT * INTO new_users FROM users"))
        assert not result.is_allowed
        assert result.rejection_code == "select_into"


class TestNoDataModifyingCteRule:
    rule = NoDataModifyingCteRule()

    def test_plain_select_passes(self):
        assert self.rule.check(_parse("SELECT * FROM t WHERE id = 1")).is_allowed

    def test_insert_at_root_passes(self):
        assert self.rule.check(_parse("INSERT INTO t (a) VALUES (1)")).is_allowed

    @pytest.mark.parametrize(
        "sql",
        [
            "WITH d AS (DELETE FROM t RETURNING *) SELECT * FROM d",
            "WITH u AS (UPDATE t SET a=1 RETURNING *) SELECT * FROM u",
            "WITH i AS (INSERT INTO t VALUES (1) RETURNING *) SELECT * FROM i",
        ],
    )
    def test_rejects_data_modifying_ctes(self, sql: str):
        result = self.rule.check(_parse(sql))
        assert not result.is_allowed
        assert result.rejection_code == "data_modifying_cte"


class TestBoundedWriteRule:
    rule = BoundedWriteRule()

    def test_select_is_not_subject_to_where_requirement(self):
        assert self.rule.check(_parse("SELECT * FROM t")).is_allowed

    def test_insert_is_not_subject_to_where_requirement(self):
        assert self.rule.check(_parse("INSERT INTO t (a) VALUES (1)")).is_allowed

    def test_bounded_update_passes(self):
        assert self.rule.check(_parse("UPDATE t SET a = 1 WHERE id = 1")).is_allowed

    def test_bounded_delete_passes(self):
        assert self.rule.check(_parse("DELETE FROM t WHERE id = 1")).is_allowed

    def test_unbounded_update_rejected(self):
        result = self.rule.check(_parse("UPDATE t SET a = 1"))
        assert not result.is_allowed
        assert result.rejection_code == "unbounded_write"

    def test_unbounded_delete_rejected(self):
        result = self.rule.check(_parse("DELETE FROM t"))
        assert not result.is_allowed
        assert result.rejection_code == "unbounded_write"


class TestNoDangerousFunctionsRule:
    rule = NoDangerousFunctionsRule()

    def test_ordinary_functions_pass(self):
        sql = "SELECT count(*), max(id), lower(name) FROM users"
        assert self.rule.check(_parse(sql)).is_allowed

    @pytest.mark.parametrize(
        "sql, expected_name",
        [
            ("SELECT pg_read_file('/etc/passwd')", "pg_read_file"),
            ("SELECT dblink_exec('h', 'DROP TABLE t')", "dblink_exec"),
            ("SELECT lo_export(0, '/tmp/x')", "lo_export"),
            ("SELECT id FROM t WHERE pg_ls_dir('/etc') IS NOT NULL", "pg_ls_dir"),
        ],
    )
    def test_rejects_dangerous_functions_anywhere(self, sql: str, expected_name: str):
        result = self.rule.check(_parse(sql))
        assert not result.is_allowed
        assert result.rejection_code == "dangerous_function"
        assert result.rejection_detail == expected_name


class TestQueryValidatorAdapter:
    validator = PostgresQueryValidatorAdapter()

    @pytest.mark.parametrize(
        "sql",
        [
            "SELECT id, email FROM users WHERE id = 1",
            "INSERT INTO orders (user_id, amount) VALUES (1, 29.99)",
            "UPDATE orders SET status = 'paid' WHERE id = 5",
            "DELETE FROM orders WHERE id = 1",
            "SELECT count(*) FROM orders WHERE status = 'paid'",
        ],
    )
    def test_legitimate_statements_pass(self, sql: str):
        assert self.validator.validate(sql).is_allowed

    @pytest.mark.parametrize(
        "sql, expected_code",
        [
            ("", "empty_query"),
            ("   \n\t  ", "empty_query"),
            ("SELEC FRO WHERE", "parse_error"),
            ("SELECT $$unterminated", "parse_error"),
            ("not valid sql $$$", "parse_error"),
            ("SELECT 1; DROP TABLE t", "multi_statement"),
            ("DROP TABLE users", "root_not_allowed"),
            ("ALTER TABLE users ADD COLUMN x INT", "root_not_allowed"),
            ("TRUNCATE users", "root_not_allowed"),
            ("CREATE TABLE x (id INT)", "root_not_allowed"),
            ("COPY users TO '/tmp/x'", "root_not_allowed"),
            ("DO $$ BEGIN PERFORM 1; END $$", "root_not_allowed"),
            ("VACUUM users", "root_not_allowed"),
            ("UPDATE users SET name = 'x'", "unbounded_write"),
            ("DELETE FROM users", "unbounded_write"),
            (
                "WITH d AS (DELETE FROM users RETURNING *) SELECT * FROM d",
                "data_modifying_cte",
            ),
            ("SELECT * INTO new_users FROM users", "select_into"),
            ("SELECT pg_read_file('/etc/passwd')", "dangerous_function"),
            (
                "SELECT id, pg_read_file('x') FROM users WHERE id = 1",
                "dangerous_function",
            ),
        ],
    )
    def test_rejections(self, sql: str, expected_code: str):
        result = self.validator.validate(sql)
        assert not result.is_allowed
        assert result.rejection_code == expected_code

    def test_validation_result_helpers(self):
        allowed = ValidationResultDto.allow()
        assert allowed.is_allowed

        rejected = ValidationResultDto.reject("x", "y")
        assert not rejected.is_allowed
        assert rejected.rejection_code == "x"
        assert rejected.rejection_detail == "y"

    def test_first_rule_to_reject_wins(self):
        result = self.validator.validate("DROP TABLE users; DROP TABLE orders")
        assert result.rejection_code == "multi_statement"

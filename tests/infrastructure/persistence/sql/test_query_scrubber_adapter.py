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

"""Unit tests for SqlQueryScrubberAdapter."""

from __future__ import annotations

import pytest

from infrastructure.persistence.sql.query_scrubber_adapter import (
    UNPARSEABLE_MARKER,
    SqlQueryScrubberAdapter,
)


class TestLogRedactorAdapter:
    scrubber = SqlQueryScrubberAdapter()

    def test_select_literals_become_placeholders(self):
        sql = "SELECT id, email FROM users WHERE id = 1 AND name = 'Alice'"
        output = self.scrubber.scrub(sql)
        assert "'Alice'" not in output
        assert "Alice" not in output
        assert "1" in output
        assert "2" in output

    def test_insert_non_sensitive_values_use_placeholders(self):
        sql = "INSERT INTO orders (user_id, amount) VALUES (1, 29.99)"
        output = self.scrubber.scrub(sql)
        assert "29.99" not in output

    def test_insert_sensitive_column_value_is_redacted(self):
        sql = (
            "INSERT INTO users (email, name, password_hash) "
            "VALUES ('carol@x.com', 'Carol', '$2b$12$secrethash')"
        )
        output = self.scrubber.scrub(sql)
        assert "secrethash" not in output
        assert "carol@x.com" not in output
        assert "[REDACTED" in output

    def test_update_sensitive_column_value_is_redacted(self):
        sql = "UPDATE users SET password_hash = 'newsecret' WHERE id = 1"
        output = self.scrubber.scrub(sql)
        assert "newsecret" not in output
        assert "[REDACTED" in output

    def test_update_mixed_columns_redacts_only_sensitive_one(self):
        sql = "UPDATE users SET password_hash = 'x', name = 'Carol' " "WHERE id = 3"
        output = self.scrubber.scrub(sql)
        assert "'x'" not in output
        assert "Carol" not in output
        assert output.count("[REDACTED") == 1

    def test_insert_from_select_sensitive_column_is_redacted(self):
        sql = (
            "INSERT INTO users (email, password_hash) "
            "SELECT 'new@x.com', 'topsecret' FROM staging WHERE id = 1"
        )
        output = self.scrubber.scrub(sql)
        assert "topsecret" not in output
        assert "[REDACTED" in output

    def test_update_tuple_assignment_sensitive_column_is_redacted(self):
        sql = (
            "UPDATE users SET (name, password_hash) = ('Carol', 'topsecret') "
            "WHERE id = 1"
        )
        output = self.scrubber.scrub(sql)
        assert "topsecret" not in output
        assert "[REDACTED" in output

    def test_api_key_column_is_redacted(self):
        sql = "UPDATE users SET api_key = 'sk_live_leaked' WHERE id = 1"
        output = self.scrubber.scrub(sql)
        assert "sk_live_leaked" not in output
        assert "[REDACTED" in output

    def test_case_insensitive_sensitive_column_match(self):
        sql = "UPDATE users SET PASSWORD_HASH = 'x' WHERE id = 1"
        output = self.scrubber.scrub(sql)
        assert "[REDACTED" in output

    def test_unparseable_sql_returns_marker(self):
        assert self.scrubber.scrub("not valid sql $$$") == UNPARSEABLE_MARKER

    def test_tokenizer_error_returns_marker(self):
        assert self.scrubber.scrub("SELECT $$unterminated") == UNPARSEABLE_MARKER

    def test_empty_input_returns_marker(self):
        assert self.scrubber.scrub("") == UNPARSEABLE_MARKER

    @pytest.mark.parametrize(
        "column_name",
        [
            "password",
            "password_hash",
            "token",
            "api_key",
            "apikey",
            "secret",
            "credential",
            "session_token",
            "private_key",
        ],
    )
    def test_various_sensitive_column_names_detected(self, column_name: str):
        sql = f"UPDATE users SET {column_name} = 'x' WHERE id = 1"
        output = self.scrubber.scrub(sql)
        assert "[REDACTED" in output

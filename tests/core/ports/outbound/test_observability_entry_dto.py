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

"""Unit tests for the ObservabilityEntryDto domain value object."""

from __future__ import annotations

from core.model.decision_enum import DecisionEnum
from core.ports.outbound.observability_entry_dto import ObservabilityEntryDto


class TestObservabilityEntry:
    def test_minimal_entry_payload_omits_optional_fields(self):
        entry = ObservabilityEntryDto(
            request_id="r1",
            decision=DecisionEnum.REJECTED,
            redacted_query="SELECT :1",
            rejection_code="multi_statement",
        )
        payload = entry.to_json_payload()
        assert payload["request_id"] == "r1"
        assert payload["decision"] == DecisionEnum.REJECTED
        assert payload["rejection_code"] == "multi_statement"
        assert "duration_ms" not in payload
        assert "db_error_message" not in payload
        assert "timestamp" in payload

    def test_full_entry_payload_includes_every_set_field(self):
        entry = ObservabilityEntryDto(
            request_id="r2",
            decision=DecisionEnum.ALLOWED,
            redacted_query="SELECT :1",
            duration_ms=12.5,
            rows_returned=3,
            rows_affected=None,
        )
        payload = entry.to_json_payload()
        assert payload["duration_ms"] == 12.5
        assert payload["rows_returned"] == 3
        assert "rows_affected" not in payload

    def test_include_result_data_false_drops_rows_and_columns(self):
        entry = ObservabilityEntryDto(
            request_id="r3",
            decision=DecisionEnum.ALLOWED,
            redacted_query="SELECT id FROM users WHERE id = :1",
            duration_ms=1.0,
            rows_returned=2,
            columns=["id", "email"],
            rows=[[1, "alice@example.com"], [2, "bob@example.com"]],
            rows_were_truncated=False,
        )
        payload = entry.to_json_payload(include_result_data=False)
        assert "rows" not in payload
        assert "columns" not in payload
        assert payload["rows_returned"] == 2
        assert payload["rows_were_truncated"] is False

    def test_include_result_data_true_keeps_rows_and_columns(self):
        entry = ObservabilityEntryDto(
            request_id="r4",
            decision=DecisionEnum.ALLOWED,
            redacted_query="SELECT id FROM users WHERE id = :1",
            columns=["id"],
            rows=[[1]],
        )
        payload = entry.to_json_payload(include_result_data=True)
        assert payload["rows"] == [[1]]
        assert payload["columns"] == ["id"]

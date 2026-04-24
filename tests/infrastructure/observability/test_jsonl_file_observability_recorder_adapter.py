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

"""Unit tests for JsonlFileObservabilityRecorderAdapter."""

from __future__ import annotations

import json

from core.model.decision_enum import DecisionEnum
from core.ports.outbound.observability_entry_dto import ObservabilityEntryDto
from infrastructure.observability.jsonl_file_observability_recorder_adapter import (
    JsonlFileObservabilityRecorderAdapter,
)


def _allowed_entry_with_rows() -> ObservabilityEntryDto:
    return ObservabilityEntryDto(
        request_id="r1",
        decision=DecisionEnum.ALLOWED,
        redacted_query="SELECT id, email FROM users WHERE id = :1",
        duration_ms=1.5,
        rows_returned=1,
        columns=["id", "email"],
        rows=[[1, "alice@example.com"]],
        rows_were_truncated=False,
    )


class TestJsonlFileRecorder:
    def test_appends_one_pii_free_line_per_entry(self, tmp_path):
        log_file = tmp_path / "observability.jsonl"
        recorder = JsonlFileObservabilityRecorderAdapter(file_path=log_file)

        recorder.record(_allowed_entry_with_rows())
        recorder.record(
            ObservabilityEntryDto(
                request_id="r2",
                decision=DecisionEnum.REJECTED,
                redacted_query="DROP TABLE users",
                rejection_code="root_not_allowed",
            )
        )

        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2

        first = json.loads(lines[0])
        assert first["request_id"] == "r1"
        assert first["decision"] == "allowed"
        assert "rows" not in first, "PII leak: rows reached JSONL file"
        assert "columns" not in first, "PII leak: columns reached JSONL file"
        assert first["rows_returned"] == 1

        second = json.loads(lines[1])
        assert second["rejection_code"] == "root_not_allowed"

    def test_no_path_is_a_noop(self, tmp_path):
        recorder = JsonlFileObservabilityRecorderAdapter(file_path=None)
        recorder.record(_allowed_entry_with_rows())
        assert list(tmp_path.iterdir()) == []

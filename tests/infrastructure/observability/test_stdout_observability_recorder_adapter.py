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

"""Unit tests for StdoutObservabilityRecorderAdapter."""

from __future__ import annotations

import io
import json

from core.model.decision_enum import DecisionEnum
from core.ports.outbound.observability_entry_dto import ObservabilityEntryDto
from infrastructure.observability.stdout_observability_recorder_adapter import (
    StdoutObservabilityRecorderAdapter,
)


class TestStdoutObservabilityRecorderAdapter:
    def test_writes_one_json_line_per_entry(self):
        stream = io.StringIO()
        recorder = StdoutObservabilityRecorderAdapter(output_stream=stream)

        recorder.record(
            ObservabilityEntryDto(
                request_id="r1",
                decision=DecisionEnum.ALLOWED,
                redacted_query="SELECT :1",
                duration_ms=1.0,
            )
        )
        recorder.record(
            ObservabilityEntryDto(
                request_id="r2",
                decision=DecisionEnum.REJECTED,
                redacted_query="SELECT :1",
                rejection_code="multi_statement",
            )
        )

        lines = stream.getvalue().strip().splitlines()
        assert len(lines) == 2

        first = json.loads(lines[0])
        second = json.loads(lines[1])
        assert first["request_id"] == "r1"
        assert first["decision"] == "allowed"
        assert second["rejection_code"] == "multi_statement"

    def test_stdout_never_emits_rows_or_columns(self):
        stream = io.StringIO()
        recorder = StdoutObservabilityRecorderAdapter(output_stream=stream)

        recorder.record(
            ObservabilityEntryDto(
                request_id="r1",
                decision=DecisionEnum.ALLOWED,
                redacted_query="SELECT id, email FROM users WHERE id = :1",
                duration_ms=2.5,
                rows_returned=1,
                columns=["id", "email"],
                rows=[[1, "alice@example.com"]],
                rows_were_truncated=False,
            )
        )

        payload = json.loads(stream.getvalue().strip())
        assert "rows" not in payload, "PII leak: rows reached stdout"
        assert "columns" not in payload, "PII leak: columns reached stdout"
        assert payload["rows_returned"] == 1
        assert payload["rows_were_truncated"] is False

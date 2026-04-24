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

"""Tests for GatewayHttpController via the shared fixtures."""

from __future__ import annotations

import io

from core.model.decision_enum import DecisionEnum
from core.ports.outbound.query_outcome_dto import QueryOutcomeDto
from core.ports.outbound.validation_result_dto import ValidationResultDto
from infrastructure.observability.stdout_observability_recorder_adapter import (
    StdoutObservabilityRecorderAdapter,
)


class TestQueryEndpoint:
    def test_rejected_query_returns_400_and_is_recorded(self, build_test_client):
        client, observability_recorder, executor = build_test_client(
            validation_result=ValidationResultDto.reject("root_not_allowed", "Drop"),
        )
        response = client.post("/query", json={"query_text": "DROP TABLE users"})
        body = response.json()
        assert response.status_code == 400
        assert body["status"] == "rejected"
        assert body["reason"] == "root_not_allowed"
        assert executor.executed == []
        assert observability_recorder.entries[0].decision == DecisionEnum.REJECTED

    def test_allowed_query_returns_200(self, build_test_client):
        client, observability_recorder, executor = build_test_client(
            query_outcome=QueryOutcomeDto(
                succeeded=True,
                columns=["id", "email"],
                rows=[[1, "a@x.com"]],
            ),
        )
        response = client.post(
            "/query",
            json={"query_text": "SELECT id, email FROM users WHERE id = 1"},
        )
        body = response.json()
        assert response.status_code == 200
        assert body["status"] == "allowed"
        assert body["result"]["rows"] == [[1, "a@x.com"]]
        assert len(executor.executed) == 1
        assert observability_recorder.entries[0].decision == DecisionEnum.ALLOWED

    def test_db_error_returns_502(self, build_test_client):
        client, observability_recorder, _ = build_test_client(
            query_outcome=QueryOutcomeDto(
                succeeded=False,
                error_message="permission denied for column password_hash",
                error_code="42501",
            ),
        )
        response = client.post(
            "/query",
            json={"query_text": "SELECT password_hash FROM users WHERE id = 1"},
        )
        body = response.json()
        assert response.status_code == 502
        assert body["status"] == "db_error"
        assert body["error_code"] == "42501"
        assert observability_recorder.entries[0].decision == DecisionEnum.DB_ERROR


class TestStdoutObservabilityRecorderAdapterIntegration:
    def test_stream_captures_decision_and_redacted_query(
        self, build_app_with_observability_recorder
    ):
        stream = io.StringIO()
        client = build_app_with_observability_recorder(
            StdoutObservabilityRecorderAdapter(output_stream=stream),
            validation_result=ValidationResultDto.reject("root_not_allowed", "Drop"),
        )
        client.post("/query", json={"query_text": "DROP TABLE t"})
        line = stream.getvalue().strip()
        assert '"decision": "rejected"' in line
        assert '"rejection_code": "root_not_allowed"' in line

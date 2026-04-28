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

"""Unit tests for ExecuteQueryUseCase (fakes only, no DB)."""

from __future__ import annotations

from application.use_cases.execute_query_use_case import (
    ExecuteQueryResultDto,
    ExecuteQueryUseCase,
)
from core.model.access_guard import AccessGuard
from core.model.decision_enum import DecisionEnum
from core.model.query_payload import QueryPayload
from core.ports.outbound.observability_entry_dto import ObservabilityEntryDto
from core.ports.outbound.query_outcome_dto import QueryOutcomeDto
from core.ports.outbound.validation_result_dto import ValidationResultDto
from infrastructure.config.settings import GatewaySettings


class RecordingObservabilityRecorder:
    def __init__(self) -> None:
        self.entries: list[ObservabilityEntryDto] = []

    def record(self, entry: ObservabilityEntryDto) -> None:
        self.entries.append(entry)


class FakeQueryValidator:
    def __init__(self, validation_result: ValidationResultDto) -> None:
        self._validation_result = validation_result
        self.calls: list[QueryPayload] = []

    def validate(self, query_text: QueryPayload) -> ValidationResultDto:
        self.calls.append(query_text)
        return self._validation_result


class FakeQueryScrubber:
    def scrub(self, query_text: QueryPayload) -> str:
        return f"<redacted:{len(query_text)}>"


class FakeQueryExecutor:
    def __init__(self, query_outcome: QueryOutcomeDto) -> None:
        self._query_outcome = query_outcome
        self.executed: list[QueryPayload] = []

    def execute(self, query_text: QueryPayload) -> QueryOutcomeDto:
        self.executed.append(query_text)
        return self._query_outcome

    def ping(self) -> bool:
        return True


def _build_use_case(
    *,
    validation_result: ValidationResultDto,
    query_outcome: QueryOutcomeDto,
    max_sample_rows_in_observability: int = 20,
):
    observability_recorder = RecordingObservabilityRecorder()
    validator = FakeQueryValidator(validation_result)
    executor = FakeQueryExecutor(query_outcome)
    guard = AccessGuard(
        validator=validator, scrubber=FakeQueryScrubber(), executor=executor
    )
    settings = GatewaySettings(
        database_adapter="postgres",
        database_url="postgresql://localhost/test",
        max_sample_rows_in_observability=max_sample_rows_in_observability,
    )
    use_case = ExecuteQueryUseCase(
        access_guard=guard,
        observability_recorder=observability_recorder,
        settings=settings,
    )
    return use_case, observability_recorder, executor, validator


class TestRejected:
    def test_rejected_query_never_reaches_executor(self):
        use_case, observability_recorder, executor, _ = _build_use_case(
            validation_result=ValidationResultDto.reject("root_not_allowed", "Drop"),
            query_outcome=QueryOutcomeDto(succeeded=True),
        )
        result = use_case.execute("DROP TABLE t", request_id="req-1")
        assert isinstance(result, ExecuteQueryResultDto)
        assert result.decision == DecisionEnum.REJECTED
        assert result.validation_result is not None
        assert result.validation_result.rejection_code == "root_not_allowed"
        assert executor.executed == []
        assert observability_recorder.entries[0].decision == DecisionEnum.REJECTED

    def test_rejected_observability_entry_has_no_duration(self):
        use_case, observability_recorder, _, _ = _build_use_case(
            validation_result=ValidationResultDto.reject("empty_query"),
            query_outcome=QueryOutcomeDto(succeeded=True),
        )
        use_case.execute("", request_id="req-2")
        assert observability_recorder.entries[0].duration_ms is None


class TestAllowed:
    def test_allowed_query_is_executed_and_recorded(self):
        use_case, observability_recorder, executor, _ = _build_use_case(
            validation_result=ValidationResultDto.allow(),
            query_outcome=QueryOutcomeDto(
                succeeded=True,
                columns=["id"],
                rows=[[1], [2]],
            ),
        )
        result = use_case.execute("SELECT id FROM t WHERE id = 1", request_id="req-3")
        assert result.decision == DecisionEnum.ALLOWED
        assert result.query_outcome is not None
        assert executor.executed == ["SELECT id FROM t WHERE id = 1"]
        assert observability_recorder.entries[0].rows_returned == 2
        assert observability_recorder.entries[0].duration_ms is not None

    def test_allowed_entry_propagates_columns_and_rows(self):
        use_case, observability_recorder, _, _ = _build_use_case(
            validation_result=ValidationResultDto.allow(),
            query_outcome=QueryOutcomeDto(
                succeeded=True,
                columns=["id", "email"],
                rows=[[1, "alice@example.com"], [2, "bob@example.com"]],
                rows_were_truncated=True,
            ),
        )
        use_case.execute("SELECT id, email FROM users", request_id="req-5")
        entry = observability_recorder.entries[0]
        assert entry.columns == ["id", "email"]
        assert entry.rows == [[1, "alice@example.com"], [2, "bob@example.com"]]
        assert entry.rows_were_truncated is True

    def test_allowed_entry_caps_rows_at_sample_limit(self):
        many_rows = [[i] for i in range(50)]
        use_case, observability_recorder, _, _ = _build_use_case(
            validation_result=ValidationResultDto.allow(),
            query_outcome=QueryOutcomeDto(
                succeeded=True,
                columns=["id"],
                rows=many_rows,
            ),
        )
        use_case.execute("SELECT id FROM t", request_id="req-6")
        entry = observability_recorder.entries[0]
        assert entry.rows_returned == 50
        assert entry.rows is not None
        assert len(entry.rows) == 20
        assert entry.rows[0] == [0]


class TestDatabaseError:
    def test_db_error_is_reported_and_recorded(self):
        use_case, observability_recorder, _, _ = _build_use_case(
            validation_result=ValidationResultDto.allow(),
            query_outcome=QueryOutcomeDto(
                succeeded=False,
                error_message="permission denied for column password_hash",
                error_code="42501",
            ),
        )
        result = use_case.execute(
            "SELECT password_hash FROM users WHERE id = 1",
            request_id="req-4",
        )
        assert result.decision == DecisionEnum.DB_ERROR
        assert observability_recorder.entries[0].db_error_code == "42501"

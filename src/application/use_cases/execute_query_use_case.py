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

"""Execute-query use case: validate, redact, execute, record one query."""

from __future__ import annotations

import time

from wireup import injectable

from core.model.access_guard import AccessGuard
from core.model.decision_enum import DecisionEnum
from core.model.query_payload import QueryPayload
from core.ports.inbound.execute_query_port import ExecuteQueryPort
from core.ports.inbound.execute_query_result_dto import ExecuteQueryResultDto
from core.ports.outbound.observability_entry_dto import ObservabilityEntryDto
from core.ports.outbound.observability_recorder import ObservabilityRecorder
from core.ports.outbound.query_outcome_dto import QueryOutcomeDto
from core.ports.outbound.validation_result_dto import ValidationResultDto
from infrastructure.config.settings import GatewaySettings


@injectable(as_type=ExecuteQueryPort)
class ExecuteQueryUseCase:
    """One call per HTTP /query request."""

    def __init__(
        self,
        access_guard: AccessGuard,
        observability_recorder: ObservabilityRecorder,
        settings: GatewaySettings,
    ) -> None:
        self._access_guard = access_guard
        self._observability_recorder = observability_recorder
        # The observability entry is kept in an in-memory ring buffer so the
        # live /observability page can render a representative sample of each
        # result. Capping the row payload here keeps memory bounded even if
        # max_results is large. The full result still goes to the HTTP
        # response.
        self._max_sample_rows_in_observability = (
            settings.max_sample_rows_in_observability
        )

    def execute(
        self, query_text: QueryPayload, request_id: str
    ) -> ExecuteQueryResultDto:
        redacted_query = self._access_guard.scrubber.scrub(query_text)

        validation_result = self._access_guard.validator.validate(query_text)
        if not validation_result.is_allowed:
            return self._record_and_return_rejected(
                request_id=request_id,
                redacted_query=redacted_query,
                validation_result=validation_result,
            )

        execution_started_at = time.perf_counter()
        query_outcome = self._access_guard.executor.execute(query_text)
        duration_ms = _milliseconds_since(execution_started_at)

        if query_outcome.succeeded:
            return self._record_and_return_allowed(
                request_id=request_id,
                redacted_query=redacted_query,
                query_outcome=query_outcome,
                duration_ms=duration_ms,
            )
        return self._record_and_return_db_error(
            request_id=request_id,
            redacted_query=redacted_query,
            query_outcome=query_outcome,
            duration_ms=duration_ms,
        )

    def _record_and_return_rejected(
        self,
        request_id: str,
        redacted_query: str,
        validation_result: ValidationResultDto,
    ) -> ExecuteQueryResultDto:
        self._observability_recorder.record(
            ObservabilityEntryDto(
                request_id=request_id,
                decision=DecisionEnum.REJECTED,
                redacted_query=redacted_query,
                rejection_code=validation_result.rejection_code,
                rejection_detail=validation_result.rejection_detail,
            )
        )
        return ExecuteQueryResultDto(
            decision=DecisionEnum.REJECTED,
            request_id=request_id,
            redacted_query=redacted_query,
            validation_result=validation_result,
        )

    def _record_and_return_allowed(
        self,
        request_id: str,
        redacted_query: str,
        query_outcome: QueryOutcomeDto,
        duration_ms: float,
    ) -> ExecuteQueryResultDto:
        sample_rows = [
            list(row)
            for row in query_outcome.rows[: self._max_sample_rows_in_observability]
        ]
        self._observability_recorder.record(
            ObservabilityEntryDto(
                request_id=request_id,
                decision=DecisionEnum.ALLOWED,
                redacted_query=redacted_query,
                duration_ms=duration_ms,
                rows_affected=query_outcome.rows_affected,
                rows_returned=len(query_outcome.rows),
                columns=list(query_outcome.columns),
                rows=sample_rows,
                rows_were_truncated=query_outcome.rows_were_truncated,
            )
        )
        return ExecuteQueryResultDto(
            decision=DecisionEnum.ALLOWED,
            request_id=request_id,
            redacted_query=redacted_query,
            duration_ms=duration_ms,
            query_outcome=query_outcome,
        )

    def _record_and_return_db_error(
        self,
        request_id: str,
        redacted_query: str,
        query_outcome: QueryOutcomeDto,
        duration_ms: float,
    ) -> ExecuteQueryResultDto:
        self._observability_recorder.record(
            ObservabilityEntryDto(
                request_id=request_id,
                decision=DecisionEnum.DB_ERROR,
                redacted_query=redacted_query,
                duration_ms=duration_ms,
                db_error_message=query_outcome.error_message,
                db_error_code=query_outcome.error_code,
            )
        )
        return ExecuteQueryResultDto(
            decision=DecisionEnum.DB_ERROR,
            request_id=request_id,
            redacted_query=redacted_query,
            duration_ms=duration_ms,
            query_outcome=query_outcome,
        )


def _milliseconds_since(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000, 2)

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

"""Shared fixtures for the controllers test suite."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from application.controllers.http.gateway.gateway_http_controller import (
    GatewayHttpController,
)
from application.controllers.http.probes.probes_http_controller import (
    ProbesHttpController,
)
from application.use_cases.check_readiness_use_case import CheckReadinessUseCase
from application.use_cases.execute_query_use_case import ExecuteQueryUseCase
from core.model.access_guard import AccessGuard
from core.model.query_payload import QueryPayload
from core.ports.outbound.observability_entry_dto import ObservabilityEntryDto
from core.ports.outbound.query_outcome_dto import QueryOutcomeDto
from core.ports.outbound.validation_result_dto import ValidationResultDto
from infrastructure.config.settings import GatewaySettings


def _test_settings() -> GatewaySettings:
    return GatewaySettings(
        database_adapter="postgres",
        database_url="postgresql://unused@localhost/unused",
    )


class _RecordingObservabilityRecorder:
    def __init__(self) -> None:
        self.entries: list[ObservabilityEntryDto] = []

    def record(self, entry: ObservabilityEntryDto) -> None:
        self.entries.append(entry)


class _FakeQueryValidator:
    def __init__(self, validation_result: ValidationResultDto) -> None:
        self._validation_result = validation_result

    def validate(self, query_text: QueryPayload) -> ValidationResultDto:
        return self._validation_result


class _FakeQueryScrubber:
    def scrub(self, query_text: QueryPayload) -> str:
        as_str = query_text if isinstance(query_text, str) else str(query_text)
        if "topsecret" in as_str:
            return as_str.replace("topsecret", "[REDACTED:$1]")
        return as_str


class _FakeQueryExecutor:
    def __init__(
        self,
        query_outcome: QueryOutcomeDto,
        ping_returns: bool = True,
    ) -> None:
        self._query_outcome = query_outcome
        self._ping_returns = ping_returns
        self.executed: list[QueryPayload] = []
        self.ping_calls = 0

    def execute(self, query_text: QueryPayload) -> QueryOutcomeDto:
        self.executed.append(query_text)
        return self._query_outcome

    def ping(self) -> bool:
        self.ping_calls += 1
        return self._ping_returns


def _assemble_app(execute_query_use_case, check_readiness_use_case) -> FastAPI:
    app = FastAPI(title="SQL Gateway")
    app.include_router(GatewayHttpController(execute_query_use_case).router)
    app.include_router(ProbesHttpController(check_readiness_use_case).router)
    return app


@pytest.fixture
def build_test_client():
    def _build(
        *,
        validation_result: ValidationResultDto = ValidationResultDto.allow(),
        query_outcome: QueryOutcomeDto | None = None,
        ping_returns: bool = True,
    ):
        outcome = query_outcome or QueryOutcomeDto(succeeded=True)
        observability_recorder = _RecordingObservabilityRecorder()
        executor = _FakeQueryExecutor(outcome, ping_returns=ping_returns)
        guard = AccessGuard(
            validator=_FakeQueryValidator(validation_result),
            scrubber=_FakeQueryScrubber(),
            executor=executor,
        )
        execute_query_use_case = ExecuteQueryUseCase(
            access_guard=guard,
            observability_recorder=observability_recorder,
            settings=_test_settings(),
        )
        check_readiness_use_case = CheckReadinessUseCase(access_guard=guard)
        app = _assemble_app(execute_query_use_case, check_readiness_use_case)
        return TestClient(app), observability_recorder, executor

    return _build


@pytest.fixture
def build_app_with_observability_recorder():
    def _build(
        observability_recorder,
        *,
        validation_result: ValidationResultDto = ValidationResultDto.allow(),
        query_outcome: QueryOutcomeDto | None = None,
    ):
        outcome = query_outcome or QueryOutcomeDto(succeeded=True)
        executor = _FakeQueryExecutor(outcome)
        guard = AccessGuard(
            validator=_FakeQueryValidator(validation_result),
            scrubber=_FakeQueryScrubber(),
            executor=executor,
        )
        execute_query_use_case = ExecuteQueryUseCase(
            access_guard=guard,
            observability_recorder=observability_recorder,
            settings=_test_settings(),
        )
        check_readiness_use_case = CheckReadinessUseCase(access_guard=guard)
        app = _assemble_app(execute_query_use_case, check_readiness_use_case)
        return TestClient(app)

    return _build

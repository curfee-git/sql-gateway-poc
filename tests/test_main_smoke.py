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

"""Smoke test for the Wireup-wired application."""

from __future__ import annotations

import sys
import types

import wireup

import application
import infrastructure.config
import infrastructure.observability
import infrastructure.persistence.postgres as postgres_module
import main as main_module
from core.model.access_guard import AccessGuard
from core.model.query_payload import QueryPayload
from core.ports.inbound.check_readiness_port import CheckReadinessPort
from core.ports.inbound.execute_query_port import ExecuteQueryPort
from core.ports.outbound.observability_recorder import ObservabilityRecorder
from core.ports.outbound.query_executor import QueryExecutor
from core.ports.outbound.query_outcome_dto import QueryOutcomeDto
from core.ports.outbound.query_scrubber import QueryScrubber
from core.ports.outbound.query_validator import QueryValidator
from core.ports.outbound.validation_result_dto import ValidationResultDto
from main import _import_submodules_recursively


def _build_container(adapter_module):
    return wireup.create_sync_container(
        injectables=[
            *_import_submodules_recursively(application),
            *_import_submodules_recursively(infrastructure.observability),
            *_import_submodules_recursively(infrastructure.config),
            *_import_submodules_recursively(adapter_module),
            main_module,
        ],
    )


class TestWireupResolution:
    def test_container_resolves_execute_query_port(self):
        container = _build_container(postgres_module)
        assert container.get(ExecuteQueryPort) is not None

    def test_container_resolves_check_readiness_port(self):
        container = _build_container(postgres_module)
        assert container.get(CheckReadinessPort) is not None

    def test_container_resolves_each_port_to_its_adapter(self):
        container = _build_container(postgres_module)
        assert container.get(QueryExecutor) is not None
        assert container.get(QueryValidator) is not None
        assert container.get(QueryScrubber) is not None
        assert container.get(ObservabilityRecorder) is not None

    def test_container_assembles_access_guard_from_ports(self):
        container = _build_container(postgres_module)
        assert isinstance(container.get(AccessGuard), AccessGuard)


class TestAdapterSwapBySignal:
    def test_importing_a_different_adapter_module_rewires_everything(self):
        fake_module = _build_fake_adapter_module()
        container = _build_container(fake_module)
        guard = container.get(AccessGuard)
        assert guard.executor.ping() is True


def _build_fake_adapter_module() -> types.ModuleType:
    """Fabricate an adapter module in memory to prove the pipeline is agnostic."""
    module = types.ModuleType("tests.fake_adapter_module")

    @wireup.injectable(as_type=QueryExecutor)
    class FakeExecutor:
        def execute(self, query_text: QueryPayload) -> QueryOutcomeDto:
            return QueryOutcomeDto(succeeded=True)

        def ping(self) -> bool:
            return True

    @wireup.injectable(as_type=QueryValidator)
    class FakeValidator:
        def validate(self, query_text: QueryPayload) -> ValidationResultDto:
            return ValidationResultDto.allow()

    @wireup.injectable(as_type=QueryScrubber)
    class FakeScrubber:
        def scrub(self, query_text: QueryPayload) -> str:
            return query_text if isinstance(query_text, str) else str(query_text)

    module.FakeExecutor = FakeExecutor
    module.FakeValidator = FakeValidator
    module.FakeScrubber = FakeScrubber
    module.__file__ = "<in-memory>"
    sys.modules[module.__name__] = module
    return module

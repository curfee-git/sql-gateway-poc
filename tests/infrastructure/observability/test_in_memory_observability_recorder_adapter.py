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

"""Unit tests for InMemoryObservabilityRecorderAdapter."""

from __future__ import annotations

import asyncio

import pytest

from core.model.decision_enum import DecisionEnum
from core.ports.outbound.observability_entry_dto import ObservabilityEntryDto
from infrastructure.observability import in_memory_observability_recorder_adapter
from infrastructure.observability.in_memory_observability_recorder_adapter import (
    InMemoryObservabilityRecorderAdapter,
)


def _make_entry(request_id: str) -> ObservabilityEntryDto:
    return ObservabilityEntryDto(
        request_id=request_id,
        decision=DecisionEnum.ALLOWED,
        redacted_query="SELECT :1",
        duration_ms=1.0,
        rows_returned=0,
    )


class TestBuffer:
    def test_record_appends_and_snapshot_returns_copy(self):
        recorder = InMemoryObservabilityRecorderAdapter()
        recorder.record(_make_entry("a"))
        recorder.record(_make_entry("b"))
        snapshot = recorder.snapshot()
        assert [entry.request_id for entry in snapshot] == ["a", "b"]
        snapshot.clear()
        assert [entry.request_id for entry in recorder.snapshot()] == ["a", "b"]

    def test_buffer_evicts_oldest_when_full(self, monkeypatch):
        monkeypatch.setattr(
            in_memory_observability_recorder_adapter, "_MAX_BUFFERED_ENTRIES", 3
        )
        recorder = InMemoryObservabilityRecorderAdapter()
        for request_id in ("a", "b", "c", "d"):
            recorder.record(_make_entry(request_id))
        assert [entry.request_id for entry in recorder.snapshot()] == ["b", "c", "d"]


class TestSubscribe:
    @pytest.mark.anyio
    async def test_new_entries_are_delivered_to_subscribers(self):
        recorder = InMemoryObservabilityRecorderAdapter()
        async with recorder.subscribe() as subscriber_queue:
            assert recorder.subscriber_count() == 1
            recorder.record(_make_entry("x"))
            entry = await asyncio.wait_for(subscriber_queue.get(), timeout=1.0)
            assert entry.request_id == "x"
        assert recorder.subscriber_count() == 0

    @pytest.mark.anyio
    async def test_subscribe_unregisters_even_if_body_raises(self):
        recorder = InMemoryObservabilityRecorderAdapter()
        with pytest.raises(RuntimeError):
            async with recorder.subscribe():
                assert recorder.subscriber_count() == 1
                raise RuntimeError("boom")
        assert recorder.subscriber_count() == 0


@pytest.fixture
def anyio_backend():
    return "asyncio"

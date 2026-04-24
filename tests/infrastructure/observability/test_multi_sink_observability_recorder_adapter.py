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

"""Unit tests for MultiSinkObservabilityRecorderAdapter."""

from __future__ import annotations

from core.model.decision_enum import DecisionEnum
from core.ports.outbound.observability_entry_dto import ObservabilityEntryDto
from infrastructure.observability.multi_sink_observability_recorder_adapter import (
    MultiSinkObservabilityRecorderAdapter,
)


class _RecordingRecorder:
    def __init__(self) -> None:
        self.entries: list[ObservabilityEntryDto] = []

    def record(self, entry: ObservabilityEntryDto) -> None:
        self.entries.append(entry)


class _BrokenRecorder:
    def record(self, entry: ObservabilityEntryDto) -> None:
        raise RuntimeError("broken pipe")


def _make_entry() -> ObservabilityEntryDto:
    return ObservabilityEntryDto(
        request_id="r1",
        decision=DecisionEnum.ALLOWED,
        redacted_query="SELECT :1",
    )


class TestFanOut:
    def test_forwards_entry_to_every_configured_recorder(self):
        first = _RecordingRecorder()
        second = _RecordingRecorder()
        multi_sink = MultiSinkObservabilityRecorderAdapter(recorders=(first, second))

        entry = _make_entry()
        multi_sink.record(entry)

        assert first.entries == [entry]
        assert second.entries == [entry]

    def test_failing_recorder_does_not_block_the_others(self, caplog):
        healthy_before = _RecordingRecorder()
        broken = _BrokenRecorder()
        healthy_after = _RecordingRecorder()
        multi_sink = MultiSinkObservabilityRecorderAdapter(
            recorders=(healthy_before, broken, healthy_after),
        )

        multi_sink.record(_make_entry())

        assert len(healthy_before.entries) == 1
        assert len(healthy_after.entries) == 1
        assert any("_BrokenRecorder failed" in rec.message for rec in caplog.records)

    def test_empty_recorder_list_is_a_no_op(self):
        multi_sink = MultiSinkObservabilityRecorderAdapter(recorders=())
        multi_sink.record(_make_entry())

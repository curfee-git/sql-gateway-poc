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

"""Fan-out observability recorder.

Forwards every entry to each downstream recorder it was configured with.
A failure in one sink is caught and logged so the remaining sinks still
receive the entry.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence

from wireup import injectable

from core.ports.outbound.observability_entry_dto import ObservabilityEntryDto
from core.ports.outbound.observability_recorder import ObservabilityRecorder
from infrastructure.observability.in_memory_observability_recorder_adapter import (
    InMemoryObservabilityRecorderAdapter,
)
from infrastructure.observability.jsonl_file_observability_recorder_adapter import (
    JsonlFileObservabilityRecorderAdapter,
)
from infrastructure.observability.stdout_observability_recorder_adapter import (
    StdoutObservabilityRecorderAdapter,
)

_logger = logging.getLogger(__name__)


class MultiSinkObservabilityRecorderAdapter:
    """Forwards each entry to every configured recorder, isolating failures."""

    def __init__(self, recorders: Iterable[ObservabilityRecorder]) -> None:
        self._recorders: Sequence[ObservabilityRecorder] = tuple(recorders)

    def record(self, entry: ObservabilityEntryDto) -> None:
        for recorder in self._recorders:
            try:
                recorder.record(entry)
            except Exception:  # noqa: BLE001
                _logger.exception(
                    "observability recorder %s failed",
                    type(recorder).__name__,
                )


@injectable(as_type=ObservabilityRecorder)
def create_multi_sink_observability_recorder_adapter(
    stdout_recorder: StdoutObservabilityRecorderAdapter,
    in_memory_recorder: InMemoryObservabilityRecorderAdapter,
    jsonl_file_recorder: JsonlFileObservabilityRecorderAdapter,
) -> ObservabilityRecorder:
    return MultiSinkObservabilityRecorderAdapter(
        recorders=(stdout_recorder, in_memory_recorder, jsonl_file_recorder),
    )

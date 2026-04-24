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

"""Stdout/JSONL observability recorder.

Intentionally **PII-free**: it drops ``rows`` and ``columns`` from the
serialized payload so production logs only carry counts, decision,
rejection reason, and timings. The in-memory recorder keeps the full
entry (see ``in_memory_observability_recorder_adapter.py``) for the live
observability page.
"""

from __future__ import annotations

import json
import sys
import threading
from typing import TextIO

from wireup import injectable

from core.ports.outbound.observability_entry_dto import ObservabilityEntryDto


class StdoutObservabilityRecorderAdapter:
    """Writes one JSON line per entry to the given stream (stdout by default)."""

    def __init__(self, output_stream: TextIO = sys.stdout) -> None:
        self._output_stream = output_stream
        self._write_lock = threading.Lock()

    def record(self, entry: ObservabilityEntryDto) -> None:
        json_line = json.dumps(entry.to_json_payload(include_result_data=False)) + "\n"
        with self._write_lock:
            self._output_stream.write(json_line)
            self._output_stream.flush()


@injectable
def create_stdout_observability_recorder_adapter() -> (
    StdoutObservabilityRecorderAdapter
):
    return StdoutObservabilityRecorderAdapter()

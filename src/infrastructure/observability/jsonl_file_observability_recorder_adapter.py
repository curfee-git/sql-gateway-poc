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

"""File-based observability recorder.

Appends one **PII-free** JSON line per entry to a configured file path, so
observability history survives gateway restarts. If no file path is
configured (``OBSERVABILITY_JSONL_PATH`` unset or empty), the recorder is
a no-op — matching the default so local dev does not unexpectedly write
files.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from wireup import injectable

from core.ports.outbound.observability_entry_dto import ObservabilityEntryDto
from infrastructure.config.settings import GatewaySettings

_logger = logging.getLogger(__name__)


class JsonlFileObservabilityRecorderAdapter:
    """Appends PII-free JSON lines to a file. No-op when no path is set."""

    def __init__(self, file_path: Path | None = None) -> None:
        self._file_path = file_path
        self._write_lock = threading.Lock()

    def record(self, entry: ObservabilityEntryDto) -> None:
        if self._file_path is None:
            return
        json_line = json.dumps(entry.to_json_payload(include_result_data=False)) + "\n"
        with self._write_lock, self._file_path.open("a", encoding="utf-8") as output_file:
            output_file.write(json_line)


@injectable
def create_jsonl_file_observability_recorder_adapter(
    settings: GatewaySettings,
) -> JsonlFileObservabilityRecorderAdapter:
    configured_path = (settings.observability_jsonl_path or "").strip()
    file_path = Path(configured_path) if configured_path else None
    if file_path is not None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        _logger.info(
            "observability JSONL sink active; appending PII-free entries to %s",
            file_path,
        )
    else:
        _logger.info(
            "observability JSONL sink disabled (OBSERVABILITY_JSONL_PATH unset)"
        )
    return JsonlFileObservabilityRecorderAdapter(file_path=file_path)

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

"""One record per served request, written to the observability recorder.

The DTO has two serialization modes:

* ``to_json_payload(include_result_data=False)`` — PII-free view used by
  the stdout/JSONL recorder. Drops ``columns`` and ``rows`` so production
  logs only carry counts and error metadata.
* ``to_json_payload(include_result_data=True)`` — full view used by the
  in-memory recorder that backs the live observability HTML. This is
  deliberate: the demo UI needs the same data ``demo_output.html``
  shows. See README section *"Live observability page and the
  rows/columns trade-off"*.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from core.model.decision_enum import DecisionEnum


@dataclass(frozen=True)
class ObservabilityEntryDto:
    request_id: str
    decision: DecisionEnum
    redacted_query: str
    rejection_code: str | None = None
    rejection_detail: str | None = None
    db_error_message: str | None = None
    db_error_code: str | None = None
    duration_ms: float | None = None
    rows_affected: int | None = None
    rows_returned: int | None = None
    columns: list[str] | None = None
    rows: list[list[Any]] | None = None
    rows_were_truncated: bool | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_json_payload(self, *, include_result_data: bool = True) -> dict[str, object]:
        payload = {key: value for key, value in asdict(self).items() if value is not None}
        if not include_result_data:
            payload.pop("rows", None)
            payload.pop("columns", None)
        return payload

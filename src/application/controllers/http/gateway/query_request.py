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

"""Request body for POST /query."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from core.model.query_payload import QueryPayload

MIN_QUERY_TEXT_LENGTH = 1
MAX_QUERY_TEXT_LENGTH = 64_000


class QueryRequest(BaseModel):
    query_text: QueryPayload = Field(
        ...,
        description=(
            "Query payload to evaluate. A SQL string for SQL adapters, "
            "a JSON document or array for NoSQL adapters. Interpretation "
            "depends on the selected database adapter."
        ),
        examples=[
            "SELECT id, email FROM users WHERE id = 1",
            "UPDATE orders SET status = 'shipped' WHERE id = 1",
            {"op": "find", "collection": "users", "filter": {"id": 1}},
        ],
    )

    @field_validator("query_text")
    @classmethod
    def _reject_empty_and_oversize(cls, value: QueryPayload) -> QueryPayload:
        if isinstance(value, str):
            if len(value) < MIN_QUERY_TEXT_LENGTH:
                raise ValueError("query_text string must not be empty")
            if len(value) > MAX_QUERY_TEXT_LENGTH:
                raise ValueError(
                    f"query_text string must be at most {MAX_QUERY_TEXT_LENGTH} chars"
                )
        elif not value:
            raise ValueError("query_text object or array must not be empty")
        return value

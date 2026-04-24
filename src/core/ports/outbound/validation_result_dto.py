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

"""Outcome of the validator layer."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationResultDto:
    """Whether a query is allowed, plus a rejection code if not."""

    is_allowed: bool
    rejection_code: str | None = None
    rejection_detail: str | None = None

    @classmethod
    def allow(cls) -> ValidationResultDto:
        return cls(is_allowed=True)

    @classmethod
    def reject(cls, code: str, detail: str | None = None) -> ValidationResultDto:
        return cls(is_allowed=False, rejection_code=code, rejection_detail=detail)

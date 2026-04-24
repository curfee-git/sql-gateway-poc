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

"""Decorator-based registry for SQL validation rules."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, TypeVar

from sqlglot import exp

from core.ports.outbound.validation_result_dto import ValidationResultDto

_SHARED_DIALECT_KEY = "_shared_"


class SqlValidationRule(Protocol):
    def check(self, statement: exp.Expression) -> ValidationResultDto: ...


_T = TypeVar("_T", bound=type[SqlValidationRule])
_classes_by_dialect: dict[str, list[type[SqlValidationRule]]] = {}
_instance_cache: dict[str, tuple[SqlValidationRule, ...]] = {}


def sql_rule(*, dialects: list[str] | None = None) -> Callable[[_T], _T]:
    """Register a rule class for the given SQL dialects (all if none given)."""

    def decorate(cls: _T) -> _T:
        if not dialects:
            _classes_by_dialect.setdefault(_SHARED_DIALECT_KEY, []).append(cls)
        else:
            for dialect in dialects:
                _classes_by_dialect.setdefault(dialect, []).append(cls)
        _instance_cache.clear()
        return cls

    return decorate


def rules_for(dialect: str) -> tuple[SqlValidationRule, ...]:
    """Return the rules that apply to ``dialect``, instantiated once each."""
    if dialect not in _instance_cache:
        shared = _classes_by_dialect.get(_SHARED_DIALECT_KEY, [])
        specific = _classes_by_dialect.get(dialect, [])
        _instance_cache[dialect] = tuple(cls() for cls in (*shared, *specific))
    return _instance_cache[dialect]

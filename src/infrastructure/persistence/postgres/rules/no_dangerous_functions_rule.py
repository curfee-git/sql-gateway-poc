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

"""Filesystem, process, and network side-effect functions are not allowed."""

from __future__ import annotations

from sqlglot import exp

from core.ports.outbound.validation_result_dto import ValidationResultDto
from infrastructure.persistence.sql.rule_registry import sql_rule


@sql_rule(dialects=["postgres"])
class NoDangerousFunctionsRule:
    DANGEROUS_FUNCTION_NAMES: frozenset[str] = frozenset(
        {
            "pg_read_file",
            "pg_read_binary_file",
            "pg_write_file",
            "pg_ls_dir",
            "pg_stat_file",
            "pg_read_server_files",
            "pg_execute_server_program",
            "dblink",
            "dblink_exec",
            "dblink_connect",
            "dblink_send_query",
            "lo_import",
            "lo_export",
            "copy_from_program",
        }
    )

    def check(self, statement: exp.Expression) -> ValidationResultDto:
        for node in statement.walk():
            if not isinstance(node, exp.Func):
                continue
            function_name = (getattr(node, "name", "") or "").lower()
            if function_name in self.DANGEROUS_FUNCTION_NAMES:
                return ValidationResultDto.reject("dangerous_function", function_name)
        return ValidationResultDto.allow()

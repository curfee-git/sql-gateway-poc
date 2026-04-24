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

"""Gateway settings plus its Wireup factory."""

from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from wireup import injectable

DEFAULT_QUERY_TIMEOUT_MS = 5_000
DEFAULT_MAX_RESULTS = 1_000
DEFAULT_MAX_SAMPLE_ROWS_IN_OBSERVABILITY = 20


class GatewaySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        frozen=True,
        populate_by_name=True,
    )

    database_adapter: str = Field(
        ...,
        validation_alias=AliasChoices("DATABASE_ADAPTER", "database_adapter"),
        description="Name of the database adapter package to load.",
    )
    database_url: str = Field(
        ...,
        description="Connection string understood by the selected adapter.",
    )
    query_timeout_ms: int = Field(
        default=DEFAULT_QUERY_TIMEOUT_MS,
        ge=1,
        description="Upper bound on how long one query may run, in milliseconds.",
    )
    max_results: int = Field(
        default=DEFAULT_MAX_RESULTS,
        ge=1,
        description="Upper bound on records returned by one read.",
    )
    max_sample_rows_in_observability: int = Field(
        default=DEFAULT_MAX_SAMPLE_ROWS_IN_OBSERVABILITY,
        ge=0,
        description=(
            "Max rows kept per allowed-query entry in the in-memory "
            "observability buffer. Column names are always kept, regardless of "
            "this value (they are metadata, not sensitive row data). Full "
            "results still flow through the HTTP response unchanged."
        ),
    )
    observability_jsonl_path: str | None = Field(
        default=None,
        description=(
            "Optional absolute path of a PII-free JSONL file to append every "
            "observability entry to. Enables history across gateway restarts. "
            "Left empty means no file sink is active."
        ),
    )


@injectable
def create_gateway_settings() -> GatewaySettings:
    return GatewaySettings()

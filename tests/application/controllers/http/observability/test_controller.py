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

"""Unit tests for ObservabilityHttpController.

The SSE streaming endpoint is exercised by the live container smoke test in
CI and by the in-memory recorder's own subscribe tests. Attempting to test
it in-process with ``httpx.AsyncClient`` + ``ASGITransport`` is unreliable
because stream disconnect propagation through Starlette's async generator
is timing-sensitive, so those tests live outside this file.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from application.controllers.http.observability.observability_http_controller import (
    ObservabilityHttpController,
)
from infrastructure.observability.in_memory_observability_recorder_adapter import (
    InMemoryObservabilityRecorderAdapter,
)


@pytest.fixture
def client_and_recorder():
    recorder = InMemoryObservabilityRecorderAdapter()
    app = FastAPI()
    app.include_router(ObservabilityHttpController(recorder).router)
    return TestClient(app), recorder


class TestHtmlPage:
    def test_page_returns_html_200_with_expected_markers(self, client_and_recorder):
        client, _ = client_and_recorder
        response = client.get("/observability")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        body = response.text
        assert "Live observability" in body
        assert "/observability/events" in body

    def test_page_advertises_the_gateway_links(self, client_and_recorder):
        client, _ = client_and_recorder
        body = client.get("/observability").text
        for expected_link in ("/docs", "/openapi.json", "/health", "/readiness"):
            assert f'href="{expected_link}"' in body

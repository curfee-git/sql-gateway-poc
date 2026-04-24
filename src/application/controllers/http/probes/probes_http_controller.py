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

"""Probes HTTP controller: class-based FastAPI handler for /health and /readiness."""

from __future__ import annotations

from http import HTTPStatus

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from wireup import injectable

from application.controllers.http.probes.health_response import HealthResponse
from application.controllers.http.probes.readiness_response import (
    DatabaseStatusEnum,
    ReadinessEnum,
    ReadinessResponse,
)
from core.ports.inbound.check_readiness_port import CheckReadinessPort
from core.ports.inbound.readiness_report_dto import ReadinessReportDto


@injectable
class ProbesHttpController:
    """Exposes liveness (/health) and readiness (/readiness) probes."""

    def __init__(self, check_readiness_port: CheckReadinessPort) -> None:
        self._check_readiness_port = check_readiness_port
        self.router = APIRouter()
        self._register_routes()

    def _register_routes(self) -> None:
        self.router.add_api_route(
            "/health",
            self._health_endpoint,
            methods=["GET"],
            response_model=HealthResponse,
        )
        self.router.add_api_route(
            "/readiness",
            self._readiness_endpoint,
            methods=["GET"],
            response_model=ReadinessResponse,
            responses={HTTPStatus.SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
        )

    @staticmethod
    def _health_endpoint() -> HealthResponse:
        return HealthResponse()

    def _readiness_endpoint(self) -> JSONResponse:
        return self._build_readiness_response(self._check_readiness_port.check())

    @staticmethod
    def _build_readiness_response(report: ReadinessReportDto) -> JSONResponse:
        payload = ReadinessResponse(
            status=ReadinessEnum.READY if report.is_ready else ReadinessEnum.NOT_READY,
            database=(
                DatabaseStatusEnum.UP if report.is_ready else DatabaseStatusEnum.DOWN
            ),
        )
        status_code = (
            HTTPStatus.OK if report.is_ready else HTTPStatus.SERVICE_UNAVAILABLE
        )
        return JSONResponse(status_code=status_code, content=payload.model_dump())

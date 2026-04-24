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

"""Gateway HTTP controller: class-based FastAPI handler for POST /query."""

from __future__ import annotations

import uuid
from http import HTTPStatus

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from wireup import injectable

from application.controllers.http.gateway.query_allowed_response import (
    QueryAllowedResponse,
)
from application.controllers.http.gateway.query_database_error_response import (
    QueryDatabaseErrorResponse,
)
from application.controllers.http.gateway.query_rejected_response import (
    QueryRejectedResponse,
)
from application.controllers.http.gateway.query_request import QueryRequest
from application.controllers.http.gateway.query_result_payload import (
    QueryResultPayload,
)
from core.model.decision_enum import DecisionEnum
from core.ports.inbound.execute_query_port import ExecuteQueryPort
from core.ports.inbound.execute_query_result_dto import ExecuteQueryResultDto

_REJECTION_MESSAGES: dict[str, str] = {
    "empty_query": "The query was empty.",
    "parse_error": "The query could not be parsed.",
    "multi_statement": "Multiple statements in one request are not allowed.",
    "root_not_allowed": (
        "Only SELECT, INSERT, UPDATE, or DELETE are allowed at the statement root."
    ),
    "forbidden_construct": (
        "DDL or transaction-control statements are not allowed anywhere in the tree."
    ),
    "select_into": "SELECT ... INTO new_table is not allowed.",
    "data_modifying_cte": "CTEs that INSERT, UPDATE, or DELETE are not allowed.",
    "unbounded_write": "UPDATE and DELETE must include a WHERE clause.",
    "dangerous_function": (
        "The query uses a filesystem, process, or network function that is blocked."
    ),
    "payload_type_mismatch": (
        "The query payload shape does not match the selected database adapter."
    ),
}


def _humanise_rejection(code: str | None) -> str:
    if not code:
        return "Query rejected."
    return _REJECTION_MESSAGES.get(code, "Query rejected.")


@injectable
class GatewayHttpController:
    """FastAPI router over the execute-query inbound port."""

    def __init__(self, execute_query_port: ExecuteQueryPort) -> None:
        self._execute_query_port = execute_query_port
        self.router = APIRouter()
        self._register_routes()

    def _register_routes(self) -> None:
        self.router.add_api_route(
            "/query",
            self._execute_query_endpoint,
            methods=["POST"],
            response_model=QueryAllowedResponse,
            responses={
                HTTPStatus.BAD_REQUEST: {"model": QueryRejectedResponse},
                HTTPStatus.BAD_GATEWAY: {"model": QueryDatabaseErrorResponse},
            },
        )

    def _execute_query_endpoint(self, request: QueryRequest) -> JSONResponse:
        result = self._execute_query_port.execute(
            query_text=request.query_text,
            request_id=str(uuid.uuid4()),
        )
        return self._build_response(result)

    def _build_response(self, result: ExecuteQueryResultDto) -> JSONResponse:
        if result.decision == DecisionEnum.REJECTED:
            return self._build_rejected_response(result)
        if result.decision == DecisionEnum.ALLOWED:
            return self._build_allowed_response(result)
        return self._build_db_error_response(result)

    @staticmethod
    def _build_rejected_response(result: ExecuteQueryResultDto) -> JSONResponse:
        assert result.validation_result is not None
        rejection_code = result.validation_result.rejection_code or ""
        payload = QueryRejectedResponse(
            request_id=result.request_id,
            reason=rejection_code,
            message=_humanise_rejection(rejection_code),
            detail=result.validation_result.rejection_detail,
        )
        return JSONResponse(
            status_code=HTTPStatus.BAD_REQUEST, content=payload.model_dump()
        )

    @staticmethod
    def _build_allowed_response(result: ExecuteQueryResultDto) -> JSONResponse:
        assert result.query_outcome is not None
        outcome = result.query_outcome
        payload = QueryAllowedResponse(
            request_id=result.request_id,
            result=QueryResultPayload(
                columns=outcome.columns,
                rows=outcome.rows,
                rows_affected=outcome.rows_affected,
                truncated=outcome.rows_were_truncated,
            ),
        )
        return JSONResponse(status_code=HTTPStatus.OK, content=payload.model_dump())

    @staticmethod
    def _build_db_error_response(result: ExecuteQueryResultDto) -> JSONResponse:
        assert result.query_outcome is not None
        outcome = result.query_outcome
        payload = QueryDatabaseErrorResponse(
            request_id=result.request_id,
            reason=outcome.error_message,
            error_code=outcome.error_code,
        )
        return JSONResponse(
            status_code=HTTPStatus.BAD_GATEWAY, content=payload.model_dump()
        )

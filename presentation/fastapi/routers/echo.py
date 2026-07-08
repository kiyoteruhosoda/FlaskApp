"""リクエスト内容をそのまま返すエコー API（FastAPI）。

Flask-Smorest 版 ``presentation/web/api/echo.py`` を移植。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse

from shared.application.authenticated_principal import AuthenticatedPrincipal
from presentation.fastapi.dependencies.auth import get_current_principal

router = APIRouter(tags=["utility"])


@router.api_route(
    "/echo",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    response_class=PlainTextResponse,
)
async def echo(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> str:
    """受信したリクエストのヘッダとボディを HTTP メッセージ形式で返す。"""
    protocol = request.scope.get("http_version", "1.1")
    query_string = request.url.query
    target = str(request.url.path)
    if query_string:
        target = f"{target}?{query_string}"

    request_line = f"{request.method} {target} HTTP/{protocol}"
    header_lines = [f"{name.decode()}: {value.decode()}" for name, value in request.headers.raw]

    body = await request.body()
    sections = [request_line, *header_lines, ""]
    if body:
        sections.append(body.decode("utf-8", "replace"))

    return "\r\n".join(sections)

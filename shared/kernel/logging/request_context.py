"""リクエスト単位の追跡コンテキスト（requestId）。

Presentation 層のミドルウェアが発行した requestId を contextvar に保持し、
リクエスト処理中に出力される全ログレコードへ自動付与するためのフィルタを
提供する。フレームワークに依存しないため、Celery ワーカー等では単に未設定の
まま動作する（request_id は付与されない）。
"""
from __future__ import annotations

import logging
from contextvars import ContextVar, Token
from typing import Optional

_request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def bind_request_id(request_id: str) -> Token:
    """現在のコンテキストに requestId を紐付け、リセット用トークンを返す。"""
    return _request_id_var.set(request_id)


def reset_request_id(token: Token) -> None:
    """``bind_request_id`` で設定した requestId を解除する。"""
    _request_id_var.reset(token)


def current_request_id() -> Optional[str]:
    """現在のコンテキストの requestId を返す（未設定なら ``None``）。"""
    return _request_id_var.get()


class RequestIdLogFilter(logging.Filter):
    """レコードに request_id が無ければ contextvar から補完するフィルタ。

    ``DBLogHandler`` は ``record.request_id`` を ``log.request_id`` 列へ保存する。
    このフィルタをハンドラに装着することで、Application 層・Infrastructure 層が
    requestId を意識せずに出力したログも API リクエストへ紐付く。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(record, "request_id", None) is None:
            request_id = current_request_id()
            if request_id is not None:
                record.request_id = request_id
        return True


__all__ = [
    "bind_request_id",
    "reset_request_id",
    "current_request_id",
    "RequestIdLogFilter",
]

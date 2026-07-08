"""Flask/FastAPI 間で共有する OAuth 一時状態ストア。

Strangler Fig 移行フェーズ用。FastAPI の ``POST /api/google/oauth/start`` が
生成した OAuth state を Flask の ``/auth/google/callback`` でも参照できるよう、
プロセス内のインメモリ辞書に保持する。

シングルプロセス(Gunicorn --workers=1 または uvicorn)であれば十分に機能する。
マルチワーカー構成では Redis 等の外部ストアへの置き換えが必要となる。
"""
from __future__ import annotations

import time
import threading
from typing import Optional

# OAuth state の有効期限（秒）。Google の同意画面の制限に合わせ 10 分。
_TTL_SECONDS = 600

_lock = threading.Lock()
# {state_token: {"data": {...}, "exp": <epoch float>}}
_store: dict[str, dict] = {}


def save_state(state_token: str, data: dict) -> None:
    """OAuth state をストアに保存する。"""
    exp = time.time() + _TTL_SECONDS
    with _lock:
        _purge_expired()
        _store[state_token] = {"data": data, "exp": exp}


def pop_state(state_token: str) -> Optional[dict]:
    """OAuth state を取得して削除する。見つからない / 期限切れの場合は ``None``。"""
    with _lock:
        _purge_expired()
        entry = _store.pop(state_token, None)
    if entry is None:
        return None
    if time.time() > entry["exp"]:
        return None
    return entry["data"]


def get_state(state_token: str) -> Optional[dict]:
    """OAuth state を参照する（削除しない）。"""
    with _lock:
        entry = _store.get(state_token)
    if entry is None:
        return None
    if time.time() > entry["exp"]:
        with _lock:
            _store.pop(state_token, None)
        return None
    return entry["data"]


def _purge_expired() -> None:
    """期限切れエントリを削除する（``_lock`` 保持中に呼ぶこと）。"""
    now = time.time()
    expired = [k for k, v in _store.items() if now > v["exp"]]
    for k in expired:
        del _store[k]


__all__ = ["save_state", "pop_state", "get_state"]

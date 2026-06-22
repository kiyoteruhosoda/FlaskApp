"""サービスログイン関連フック (廃止済み).

サービスアカウントはステートレス Bearer トークン認証に移行済みのため、
セッションベースのスコープ適用フックは削除された。
このモジュールは互換性のために存在するが、実質的な処理は行わない。
"""

from __future__ import annotations

from flask import Flask


def register_service_login_hooks(app: Flask) -> None:
    """サービスログインフックを登録する（現在は no-op）。"""

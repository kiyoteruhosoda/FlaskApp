"""``TokenService.resolve_granted_scope``（scope交付ルールの唯一の出所）のユニットテスト。

ログイン（``POST /api/auth/login``）とトークンリフレッシュ
（``POST /api/auth/refresh``）の両方がこの関数で交付 scope を決定する。
契約（CLAUDE.md）: 交付は保有権限の範囲内・未指定/空 = 権限なし。
``gui:view`` を要求し保有するセッション（ブラウザSPA）は全保有権限を交付する。
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("DATABASE_URI", "sqlite:///:memory:")

from presentation.fastapi.services.token_service import TokenService  # noqa: E402


@pytest.mark.unit
class TestResolveGrantedScope:
    def test_gui_view_request_grants_all_held_permissions(self):
        granted = TokenService.resolve_granted_scope(
            ["gui:view"], {"gui:view", "wiki:admin", "user:manage"}
        )
        assert granted == ["gui:view", "user:manage", "wiki:admin"]

    def test_empty_request_grants_nothing(self):
        assert TokenService.resolve_granted_scope([], {"gui:view", "wiki:admin"}) == []

    def test_narrow_request_grants_intersection_only(self):
        granted = TokenService.resolve_granted_scope(
            ["wiki:read", "wiki:admin"], {"wiki:read", "media:view"}
        )
        assert granted == ["wiki:read"]

    def test_gui_view_request_without_holding_it_does_not_expand(self):
        """gui:view を保有しないユーザーが要求しても全権限拡張は起きない。"""
        granted = TokenService.resolve_granted_scope(
            ["gui:view", "media:view"], {"media:view", "album:view"}
        )
        assert granted == ["media:view"]

    def test_request_for_unheld_permissions_grants_nothing(self):
        assert (
            TokenService.resolve_granted_scope(["admin:system-settings"], set()) == []
        )

    def test_whitespace_and_empty_items_are_ignored(self):
        granted = TokenService.resolve_granted_scope(
            ["  ", "", "media:view "], {"media:view"}
        )
        assert granted == ["media:view"]

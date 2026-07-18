"""ロール選択フロー（GET /api/auth/roles → POST /api/auth/select-role）の回帰テスト。

過去、フロントエンドのロール選択画面（``frontend/src/pages/RoleSelectionPage.tsx``）
は ``GET /api/auth/roles`` からロール候補を取得するが、FastAPI 移行後の
バックエンドにこのエンドポイントが存在せず 404 となり、複数ロール保有者に
「Select Role」画面は表示されるのに候補が1件も出ない状態だった。

本テストは実DB（migrations 適用済み）＋実 FastAPI アプリで、

1. 複数ロール保有者のログインで ``requires_role_selection`` が true になること
2. ``GET /api/auth/roles`` が全ロール候補を返すこと
3. ``POST /api/auth/select-role`` で選択後、scope が選択ロールの権限に絞られ、
   ``GET /api/auth/roles`` の ``active_role_id`` に選択が反映されること

を一気通貫で検証する。
"""
from __future__ import annotations

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from tests.integration.fastapi.test_login_grants_working_admin_access import (
    admin_client,  # noqa: F401 - pytest fixture
)


def _grant_role_to_admin(client: TestClient, role_name: str) -> None:
    """テスト用: 初期管理者ユーザーにロールを追加で付与する。"""
    from shared.kernel.database.session import get_db

    override = client.app.dependency_overrides[get_db]
    gen = override()
    db = next(gen)
    try:
        db.execute(
            sa.text(
                "INSERT INTO user_roles (user_id, role_id) "
                "SELECT :user_id, id FROM role WHERE name = :role_name"
            ),
            {"user_id": 1, "role_name": role_name},
        )
        db.commit()
    finally:
        gen.close()


def _login(client: TestClient) -> dict:
    from shared.domain.auth.master_data import DEFAULT_ADMIN_EMAIL

    resp = client.post(
        "/api/auth/login",
        json={"email": DEFAULT_ADMIN_EMAIL, "password": "admin", "scope": ["gui:view"]},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.integration
def test_single_role_user_does_not_require_selection(admin_client: TestClient) -> None:
    """単一ロールのユーザーはロール選択不要（requires_selection=false）。"""
    body = _login(admin_client)
    assert body["requires_role_selection"] is False

    roles_resp = admin_client.get(
        "/api/auth/roles",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert roles_resp.status_code == 200, roles_resp.text
    data = roles_resp.json()
    assert [r["name"] for r in data["roles"]] == ["admin"]
    assert data["requires_selection"] is False


@pytest.mark.integration
def test_multi_role_user_gets_role_candidates_and_can_select(
    admin_client: TestClient,
) -> None:
    """複数ロール保有者にロール候補が返り、選択でトークンが再発行されること。

    回帰: エンドポイント未実装（404）によりロール選択画面の候補が
    空になっていた不具合の再発防止。
    """
    from shared.domain.auth.master_data import ROLE_PERMISSIONS

    _grant_role_to_admin(admin_client, "member")

    body = _login(admin_client)
    assert body["requires_role_selection"] is True

    headers = {"Authorization": f"Bearer {body['access_token']}"}

    # ロール候補が全件（admin, member）返る
    roles_resp = admin_client.get("/api/auth/roles", headers=headers)
    assert roles_resp.status_code == 200, roles_resp.text
    data = roles_resp.json()
    role_names = {r["name"] for r in data["roles"]}
    assert role_names == {"admin", "member"}
    assert data["requires_selection"] is True

    # 各候補には権限リストが含まれる（画面の説明表示に使用）
    member_role = next(r for r in data["roles"] if r["name"] == "member")
    assert set(member_role["permissions"]) == set(ROLE_PERMISSIONS["member"])

    # member ロールを選択 → scope が member の権限に絞られたトークンが発行される
    select_resp = admin_client.post(
        "/api/auth/select-role",
        json={"role_id": member_role["id"]},
        headers=headers,
    )
    assert select_resp.status_code == 200, select_resp.text
    selected = select_resp.json()
    assert selected["role"]["name"] == "member"
    assert set(selected["scope"].split()) == set(ROLE_PERMISSIONS["member"])

    # 再発行トークンで /roles を叩くと選択済みロールが active_role_id に反映される
    new_headers = {"Authorization": f"Bearer {selected['access_token']}"}
    roles_resp2 = admin_client.get("/api/auth/roles", headers=new_headers)
    assert roles_resp2.status_code == 200, roles_resp2.text
    assert roles_resp2.json()["active_role_id"] == member_role["id"]


@pytest.mark.integration
def test_select_role_rejects_role_not_held(admin_client: TestClient) -> None:
    """保有していないロールIDの選択は 400 invalid_role。"""
    body = _login(admin_client)
    resp = admin_client.post(
        "/api/auth/select-role",
        json={"role_id": 999},
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "invalid_role"

"""認可マスタデータの正本（ユビキタス言語: ロール / 権限 / 権限付与）。

ロール・権限コード・ロールへの権限付与・初期管理者は、アプリケーションが
起動時から正しく動作するために必須の「マスタデータ」である。値の重複定義に
よるドリフトを防ぐため、ここを唯一の出所（single source of truth）とし、

- マイグレーション（``migrations/versions/*_seed_master_data.py``）
- 投入スクリプト（``scripts/seed_master_data.py``）

の双方がこのモジュールを参照する。フレームワーク・DB に依存しない純データの
ため、どこからでも安全に import できる。
"""
from __future__ import annotations

from typing import Mapping, Sequence

# --- ロール ------------------------------------------------------------------
# id は外部参照（user_roles 等）の安定キーとして固定する。
ROLES: Sequence[tuple[int, str]] = (
    (1, "admin"),
    (2, "manager"),
    (3, "member"),
    (4, "guest"),
)

# --- 権限コード（scope） -----------------------------------------------------
# 認可は scope（権限コード値）で行う。コードを安定キーとし、id は DB 採番に任せる。
PERMISSION_CODES: Sequence[str] = (
    "admin:photo-settings",
    "admin:job-settings",
    "admin:system-settings",
    "user:manage",
    "album:create",
    "album:edit",
    "album:view",
    "media:view",
    "media:session",
    "group:manage",
    "permission:manage",
    "role:manage",
    "system:manage",
    "wiki:admin",
    "wiki:read",
    "wiki:write",
    "media:tag-manage",
    "media:metadata-manage",
    "media:delete",
    "media:recover",
    "totp:view",
    "totp:write",
    "service_account:manage",
    "certificate:manage",
    "api_key:manage",
    "certificate:sign",
    "api_key:read",
    "dashboard:view",
    "gui:view",
    "admin:impersonate",
)

# --- ロールへの権限付与 ------------------------------------------------------
# ロール名 -> 付与する権限コードの集合。有効 scope は所属ロールの和集合。
ROLE_PERMISSIONS: Mapping[str, Sequence[str]] = {
    "admin": tuple(PERMISSION_CODES),  # 全権限
    "manager": (
        "admin:photo-settings",
        "album:create",
        "album:edit",
        "album:view",
        "media:view",
        "media:session",
        "media:tag-manage",
        "media:metadata-manage",
        "media:delete",
        "media:recover",
        "dashboard:view",
        "gui:view",
    ),
    "member": (
        "album:view",
        "media:view",
        "dashboard:view",
        "gui:view",
    ),
    "guest": (
        "dashboard:view",
        "gui:view",
    ),
}

# --- 初期管理者 --------------------------------------------------------------
# パスワードは環境変数 ``ADMIN_INITIAL_PASSWORD`` で上書きできる（推奨）。
# 未指定時はこのフォールバックハッシュ（平文 "admin"）が使われるため、
# 本番では初回ログイン後に必ず変更すること。
DEFAULT_ADMIN_ID: int = 1
DEFAULT_ADMIN_EMAIL: str = "admin@example.com"
DEFAULT_ADMIN_USERNAME: str = "admin"
DEFAULT_ADMIN_ROLE: str = "admin"
DEFAULT_ADMIN_PASSWORD_HASH: str = (
    "scrypt:32768:8:1$7oTcIUdekNLXGSXC$"
    "fd0f3320bde4570c7e1ea9d9d289aeb916db7a50fb62489a7e89d99c6cc576813506fd99"
    "f50904101c1eb85ff925f8dc879df5ded781ef2613224d702938c9c8"
)

__all__ = [
    "ROLES",
    "PERMISSION_CODES",
    "ROLE_PERMISSIONS",
    "DEFAULT_ADMIN_ID",
    "DEFAULT_ADMIN_EMAIL",
    "DEFAULT_ADMIN_USERNAME",
    "DEFAULT_ADMIN_ROLE",
    "DEFAULT_ADMIN_PASSWORD_HASH",
]

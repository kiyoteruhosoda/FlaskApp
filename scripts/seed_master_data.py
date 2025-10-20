#!/usr/bin/env python3
"""
マスタデータシード投入スクリプト
Usage: python scripts/seed_master_data.py
"""
import sys
import os
from datetime import datetime, timezone

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.db import db
from core.models.user import User, Role, Permission
from core.models.system_setting import SystemSetting
from core.system_settings_defaults import (
    DEFAULT_APPLICATION_SETTINGS,
    DEFAULT_CORS_SETTINGS,
)
from flask_babel import gettext as _
from webapp import create_app
from webapp.services.system_setting_service import SystemSettingService


def seed_system_settings():
    """システム設定マスタデータの投入"""

    def _ensure_setting(key: str, payload: dict, description: str) -> None:
        existing = SystemSetting.query.filter_by(setting_key=key).first()
        if existing:
            print(f"System setting already exists: {key}")
            return
        payload_copy = {}
        for setting_name, value in dict(payload).items():
            if isinstance(value, list):
                payload_copy[setting_name] = list(value)
            elif isinstance(value, dict):
                payload_copy[setting_name] = dict(value)
            else:
                payload_copy[setting_name] = value
        record = SystemSetting(
            setting_key=key,
            setting_json=payload_copy,
            description=description,
        )
        db.session.add(record)
        print(f"Added system setting: {key}")

    _ensure_setting(
        SystemSettingService._APPLICATION_CONFIG_KEY,
        DEFAULT_APPLICATION_SETTINGS,
        "Application configuration values.",
    )
    _ensure_setting(
        SystemSettingService._CORS_CONFIG_KEY,
        DEFAULT_CORS_SETTINGS,
        "CORS configuration.",
    )


def seed_roles():
    """ロールマスタデータの投入"""
    roles_data = [
        {'id': 1, 'name': 'admin'},
        {'id': 2, 'name': 'manager'},
        {'id': 3, 'name': 'member'},
        {'id': 4, 'name': 'guest'}
    ]
    
    for role_data in roles_data:
        existing_role = Role.query.filter_by(id=role_data['id']).first()
        if not existing_role:
            role = Role(**role_data)
            db.session.add(role)
            print(f"Added role: {role_data['name']}")
        else:
            print(f"Role already exists: {role_data['name']}")


def seed_permissions():
    """権限マスタデータの投入"""
    permissions_data = [
        {'id': 1, 'code': 'admin:photo-settings'},
        {'id': 2, 'code': 'admin:job-settings'},
        {'id': 3, 'code': 'user:manage'},
        {'id': 4, 'code': 'album:create'},
        {'id': 5, 'code': 'album:edit'},
        {'id': 6, 'code': 'album:view'},
        {'id': 7, 'code': 'media:view'},
        {'id': 8, 'code': 'permission:manage'},
        {'id': 9, 'code': 'role:manage'},
        {'id': 10, 'code': 'system:manage'},
        {'id': 11, 'code': 'wiki:admin'},
        {'id': 12, 'code': 'wiki:read'},
        {'id': 13, 'code': 'wiki:write'},
        {'id': 14, 'code': 'media:tag-manage'},
        {'id': 15, 'code': 'media:delete'},
        {'id': 16, 'code': 'media:recover'},
        {'id': 17, 'code': 'totp:view'},
        {'id': 18, 'code': 'totp:write'},
        {'id': 19, 'code': 'service_account:manage'},
        {'id': 20, 'code': 'certificate:manage'},
        {'id': 21, 'code': 'certificate:sign'},
        {'id': 23, 'code': 'api_key:read'},
        {'id': 24, 'code': 'api_key:manage'},
    ]
    
    for perm_data in permissions_data:
        existing_perm = Permission.query.filter_by(id=perm_data['id']).first()
        if not existing_perm:
            permission = Permission(**perm_data)
            db.session.add(permission)
            print(f"Added permission: {perm_data['code']}")
        else:
            print(f"Permission already exists: {perm_data['code']}")


def seed_role_permissions():
    """ロール権限関係の投入"""
    role_permissions_data = [
        # admin (role_id=1) - all permissions
        (1, 1), (1, 2), (1, 3), (1, 4), (1, 5),
        (1, 6), (1, 7), (1, 8), (1, 9), (1, 10),
        (1, 11), (1, 12), (1, 13), (1, 14), (1, 15), (1, 16), (1, 17), (1, 18), (1, 19), (1, 20), (1, 21), (1, 23), (1, 24),
        # manager (role_id=2) - limited permissions
        (2, 1), (2, 4), (2, 5), (2, 6), (2, 7), (2, 14), (2, 15), (2, 16),
        # member (role_id=3) - view only
        (3, 6), (3, 7)
    ]
    
    for role_id, perm_id in role_permissions_data:
        role = Role.query.get(role_id)
        permission = Permission.query.get(perm_id)
        
        if role and permission and permission not in role.permissions:
            role.permissions.append(permission)
            print(f"Added permission '{permission.code}' to role '{role.name}'")


def seed_admin_user():
    """管理者ユーザーの投入"""
    admin_email = "admin@example.com"
    # デフォルトパスワード（実際の運用では変更必須）
    admin_password_hash = "scrypt:32768:8:1$7oTcIUdekNLXGSXC$fd0f3320bde4570c7e1ea9d9d289aeb916db7a50fb62489a7e89d99c6cc576813506fd99f50904101c1eb85ff925f8dc879df5ded781ef2613224d702938c9c8"
    
    existing_user = User.query.filter_by(email=admin_email).first()
    if not existing_user:
        admin_user = User(
            id=1,
            email=admin_email,
            password_hash=admin_password_hash,
            created_at=datetime.now(timezone.utc),
            is_active=True
        )
        db.session.add(admin_user)
        
        # adminロールを付与
        admin_role = Role.query.filter_by(name='admin').first()
        if admin_role:
            admin_user.roles.append(admin_role)
        
        print(f"Added admin user: {admin_email}")
    else:
        print(f"Admin user already exists: {admin_email}")


def main():
    """メインのシード実行"""
    app = create_app()
    
    with app.app_context():
        print(_("=== %(app_name)s Master Data Seeding ===", app_name=_("AppName")))
        
        try:
            # システム設定投入
            print("\n1. Seeding system settings...")
            seed_system_settings()

            # ロールデータ投入
            print("\n2. Seeding roles...")
            seed_roles()

            # 権限データ投入
            print("\n3. Seeding permissions...")
            seed_permissions()

            # 一度コミットして関係テーブルの前提データを確定
            db.session.commit()

            # ロール権限関係投入
            print("\n4. Seeding role-permission relationships...")
            seed_role_permissions()

            # 管理者ユーザー投入
            print("\n5. Seeding admin user...")
            seed_admin_user()
            
            # 最終コミット
            db.session.commit()
            print("\n=== Seeding completed successfully! ===")
            
        except Exception as e:
            db.session.rollback()
            print(f"\n=== Seeding failed: {e} ===")
            sys.exit(1)


if __name__ == "__main__":
    main()

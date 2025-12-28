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
    permission_codes = [
        'admin:photo-settings',
        'admin:job-settings',
        'user:manage',
        'album:create',
        'album:edit',
        'album:view',
        'media:view',
        'permission:manage',
        'role:manage',
        'system:manage',
        'wiki:admin',
        'wiki:read',
        'wiki:write',
        'media:tag-manage',
        'media:metadata-manage',
        'media:delete',
        'media:recover',
        'totp:view',
        'totp:write',
        'service_account:manage',
        'certificate:manage',
        'api_key:manage',
        'certificate:sign',
        'api_key:read',
        'dashboard:view',
        'gui:view',
    ]

    for code in permission_codes:
        existing_perm = Permission.query.filter_by(code=code).first()
        if existing_perm:
            print(f"Permission already exists: {code}")
            continue

        permission = Permission(code=code)
        db.session.add(permission)
        print(f"Added permission: {code}")


def seed_role_permissions():
    """ロール権限関係の投入"""
    role_permissions_map = {
        'admin': [
            'admin:photo-settings',
            'admin:job-settings',
            'user:manage',
            'album:create',
            'album:edit',
            'album:view',
            'media:view',
            'permission:manage',
            'role:manage',
            'system:manage',
            'wiki:admin',
            'wiki:read',
            'wiki:write',
            'media:tag-manage',
            'media:metadata-manage',
            'media:delete',
            'media:recover',
            'totp:view',
            'totp:write',
            'service_account:manage',
            'certificate:manage',
            'api_key:manage',
            'certificate:sign',
            'api_key:read',
            'dashboard:view',
            'gui:view',
        ],
        'manager': [
            'admin:photo-settings',
            'album:create',
            'album:edit',
            'album:view',
            'media:view',
            'media:tag-manage',
            'media:metadata-manage',
            'media:delete',
            'media:recover',
            'dashboard:view',
            'gui:view',
        ],
        'member': [
            'album:view',
            'media:view',
            'dashboard:view',
            'gui:view',
        ],
        'guest': [
            'dashboard:view',
            'gui:view',
        ],
    }

    all_permission_codes = {
        code for codes in role_permissions_map.values() for code in codes
    }
    permissions_by_code = {
        permission.code: permission
        for permission in Permission.query.filter(
            Permission.code.in_(all_permission_codes)
        ).all()
    }

    for role_name, codes in role_permissions_map.items():
        role = Role.query.filter_by(name=role_name).first()
        if not role:
            print(f"Role not found: {role_name}")
            continue

        for code in sorted(set(codes)):
            permission = permissions_by_code.get(code)
            if not permission:
                print(f"Permission '{code}' not found for role '{role_name}'")
                continue
            if permission in role.permissions:
                continue
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

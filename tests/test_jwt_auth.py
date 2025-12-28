#!/usr/bin/env python3
"""
JWT Bearer認証のテスト用スクリプト
"""

import sys
import os
sys.path.append('/home/kyon/myproject')

from webapp import create_app
import jwt
import requests
import json
from datetime import datetime, timedelta

def main():
    # Flaskアプリの作成
    app = create_app()
    
    with app.app_context():
        # JWT設定の確認
        print("=== JWT設定確認 ===")
        print(f"JWT_SECRET_KEY: {app.config.get('JWT_SECRET_KEY', 'NOT_SET')}")
        
        # ユーザー情報の確認
        from core.models.user import User
        user = User.query.filter_by(email='admin@example.com').first()
        if user:
            print(f"ユーザー存在確認: {user.email} (ID: {user.id}, Active: {user.is_active})")
            
            # JWTトークンの手動生成
            payload = {
                'sub': str(user.id),  # 文字列に変換
                'email': user.email,
                'exp': datetime.utcnow() + timedelta(hours=1),
                'iss': app.config.get('ACCESS_TOKEN_ISSUER', 'fpv-webapp'),
                'aud': app.config.get('ACCESS_TOKEN_AUDIENCE', 'fpv-webapp'),
            }
            
            token = jwt.encode(
                payload,
                app.config['JWT_SECRET_KEY'],
                algorithm='HS256'
            )
            
            print(f"生成したトークン（50文字）: {token[:50]}...")
            
            # トークンのデコードテスト
            try:
                decoded = jwt.decode(
                    token,
                    app.config['JWT_SECRET_KEY'],
                    algorithms=['HS256'],
                    audience=app.config.get('ACCESS_TOKEN_AUDIENCE'),
                    issuer=app.config.get('ACCESS_TOKEN_ISSUER'),
                )
                print(f"デコード成功: {decoded}")
            except Exception as e:
                print(f"デコードエラー: {e}")
        
        else:
            print("admin@example.com ユーザーが見つかりません")
            # ユーザー一覧を表示
            users = User.query.all()
            print("登録されているユーザー:")
            for u in users:
                print(f"  - {u.email} (ID: {u.id}, Active: {u.is_active})")

if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
既存ユーザーにusernameフィールドを設定するスクリプト
"""

import sys
import os

# パスを追加してプロジェクトモジュールをインポート可能にする
sys.path.insert(0, os.path.abspath('.'))

from webapp import create_app
from core.db import db
from core.models.user import User


def add_usernames():
    """既存ユーザーにusernameを設定"""
    app = create_app()
    
    with app.app_context():
        try:
            # データベースにusernameカラムが存在するかチェック
            try:
                # まず、usernameカラムを追加（既に存在する場合はエラーを無視）
                with db.engine.connect() as conn:
                    conn.execute(db.text("ALTER TABLE user ADD COLUMN username VARCHAR(80)"))
                    conn.commit()
                print("✓ usernameカラムを追加しました")
            except Exception as e:
                print(f"usernameカラムの追加をスキップ（既に存在する可能性）: {e}")
            
            # 既存のユーザーを取得
            users = User.query.all()
            print(f"\n既存ユーザー数: {len(users)}")
            
            for user in users:
                if not user.username and user.email:
                    # emailのローカル部分をusernameとして設定
                    username = user.email.split('@')[0]
                    user.username = username
                    print(f"ユーザーID {user.id}: {user.email} -> username: {username}")
            
            # 変更をコミット
            db.session.commit()
            print(f"\n✓ {len(users)}人のユーザーにusernameを設定しました")
            
            # 結果確認
            print("\n=== 更新後のユーザー一覧 ===")
            for user in User.query.all():
                print(f"ID: {user.id}, Email: {user.email}, Username: {user.username}, Display: {user.display_name}")
                
        except Exception as e:
            db.session.rollback()
            print(f"❌ エラーが発生しました: {e}")
            return False
    
    return True


if __name__ == "__main__":
    print("既存ユーザーにusernameを設定します...")
    if add_usernames():
        print("✓ 完了しました")
    else:
        print("❌ 失敗しました")

#!/usr/bin/env python3
"""
Flask アプリケーションコンテキストでページネーション修正をテスト
"""
import os
import sys

# プロジェクトパスを追加
sys.path.insert(0, os.path.abspath('.'))

from webapp import create_app
from core.db import db

def test_pagination_fix():
    """Flask アプリケーションコンテキストでページネーション修正をテスト"""
    
    # Flaskアプリケーションを作成
    app = create_app()
    
    with app.app_context():
        print("ページネーション修正のテスト開始")
        
        from webapp.api.picker_session_service import PickerSessionService
        from webapp.api.pagination import PaginationParams
        from core.models.picker_session import PickerSession
        
        # 既存のPickerSessionを取得
        ps = db.session.query(PickerSession).filter(
            PickerSession.session_id == "313bc13c-9fd0-4314-868c-93092a38585b"
        ).first()
        
        if not ps:
            print("❌ テスト対象のPickerSessionが見つからない")
            return False
        
        print(f"📋 PickerSession found: ID={ps.id}, session_id={ps.session_id}")
        
        # PaginationParamsを作成
        params = PaginationParams(page_size=1, use_cursor=True)
        
        try:
            # selection_detailsメソッドを呼び出し
            result = PickerSessionService.selection_details(ps, params)
            print("✅ ページネーション修正が成功: エラーなく実行完了")
            print(f"結果キー: {list(result.keys())}")
            
            if 'selections' in result:
                print(f"選択項目数: {len(result['selections'])}")
                if result['selections']:
                    print(f"最初の選択項目: {result['selections'][0].get('id', 'N/A')}")
            
            if 'pagination' in result:
                pagination = result['pagination']
                print(f"ページネーション: hasNext={pagination.get('hasNext')}, hasPrev={pagination.get('hasPrev')}")
            
            return True
            
        except AttributeError as e:
            if "'id'" in str(e):
                print("❌ ページネーション修正が失敗: まだ'id'属性エラーが発生")
                print(f"エラー: {e}")
                return False
            else:
                print(f"❌ 予期しないAttributeError: {e}")
                return False
        except Exception as e:
            print(f"❌ その他のエラー: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return False

if __name__ == "__main__":
    success = test_pagination_fix()
    sys.exit(0 if success else 1)

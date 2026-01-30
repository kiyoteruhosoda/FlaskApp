#!/usr/bin/env python3
"""
ページネーション修正のテストスクリプト
"""
import os
import sys
from unittest.mock import MagicMock

# プロジェクトパスを追加
sys.path.insert(0, os.path.abspath('.'))

from webapp.api.picker_session_service import PickerSessionService
from webapp.api.pagination import PaginationParams
from core.models.picker_session import PickerSession
from core.models.photo_models import PickerSelection

def test_pagination_fix():
    """ページネーション修正をテスト"""
    print("ページネーション修正のテスト開始")
    
    # モックのPickerSessionを作成
    mock_ps = MagicMock(spec=PickerSession)
    mock_ps.id = 39
    mock_ps.session_id = "313bc13c-9fd0-4314-868c-93092a38585b"
    
    # PaginationParamsを作成
    params = PaginationParams(page_size=1, use_cursor=True)
    
    try:
        # selection_detailsメソッドを呼び出し
        result = PickerSessionService.selection_details(mock_ps, params)
        print("✅ ページネーション修正が成功: エラーなく実行完了")
        print(f"結果キー: {list(result.keys())}")
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
        print(f"❌ その他のエラー: {e}")
        return False

if __name__ == "__main__":
    test_pagination_fix()

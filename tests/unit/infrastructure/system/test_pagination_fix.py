#!/usr/bin/env python3
"""
ページネーション修正のテストスクリプト
"""
import os
import sys
from unittest.mock import MagicMock

# プロジェクトパスを追加
sys.path.insert(0, os.path.abspath('.'))

from presentation.web.api.picker_session_service import PickerSessionService
from presentation.web.api.pagination import PaginationParams
from bounded_contexts.picker_import.infrastructure.picker_session import PickerSession
from bounded_contexts.photonest.infrastructure.photo_models import PickerSelection

def test_pagination_fix(app_context):
    """ページネーション修正をテスト（'id' 属性エラーが再発せず、辞書を返すこと）。"""
    # モックのPickerSessionを作成
    mock_ps = MagicMock(spec=PickerSession)
    mock_ps.id = 39
    mock_ps.session_id = "313bc13c-9fd0-4314-868c-93092a38585b"

    # PaginationParamsを作成
    params = PaginationParams(page_size=1, use_cursor=True)

    # アプリケーションコンテキスト内で selection_details を呼び出す
    result = PickerSessionService.selection_details(mock_ps, params)

    assert isinstance(result, dict)

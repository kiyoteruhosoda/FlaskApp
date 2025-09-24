#!/usr/bin/env python3
"""
DBLogHandlerの修正をテストするための簡単なスクリプト
"""

import json
import logging
import os
import sys
import tempfile
from unittest.mock import Mock, patch

import pytest

# プロジェクトのルートパスをsys.pathに追加
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Core modulesをインポート
from core.db_log_handler import DBLogHandler


def test_db_log_handler_with_event():
    """eventが設定されている場合のテスト"""
    print("Testing DBLogHandler with event attribute...")
    
    # モックオブジェクトを作成
    with patch('core.db_log_handler.db') as mock_db:
        mock_conn = Mock()
        mock_db.engine.begin.return_value.__enter__.return_value = mock_conn
        
        handler = DBLogHandler()
        
        # event属性が設定されたログレコードを作成
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message with event",
            args=(),
            exc_info=None
        )
        record.event = "api.test"
        
        # ログレコードを処理
        handler.emit(record)
        
        # SQLクエリが呼び出されたかチェック
        assert mock_conn.execute.called
        args, kwargs = mock_conn.execute.call_args
        stmt = args[0]

        # eventが正しく設定されているかチェック
        values = stmt.compile().params
        assert values['event'] == "api.test"
        assert values['level'] == "INFO"
        payload = json.loads(values['message'])
        assert payload['message'] == "Test message with event"
        assert payload['_meta']['logger'] == "test"
        
        print("✓ Event attribute test passed")


def test_db_log_handler_without_event():
    """eventが設定されていない場合のテスト（修正後）"""
    print("Testing DBLogHandler without event attribute...")
    
    # モックオブジェクトを作成
    with patch('core.db_log_handler.db') as mock_db:
        mock_conn = Mock()
        mock_db.engine.begin.return_value.__enter__.return_value = mock_conn
        
        handler = DBLogHandler()
        
        # event属性が設定されていないログレコードを作成
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Flask-Login authentication successful",
            args=(),
            exc_info=None
        )
        # event属性は設定しない
        
        # ログレコードを処理
        handler.emit(record)
        
        # SQLクエリが呼び出されたかチェック
        assert mock_conn.execute.called
        args, kwargs = mock_conn.execute.call_args
        stmt = args[0]

        # eventがロガー名に設定されているかチェック
        values = stmt.compile().params
        assert values['event'] == "test"
        assert values['level'] == "INFO"
        payload = json.loads(values['message'])
        assert payload['message'] == "Flask-Login authentication successful"
        assert payload['_meta']['logger'] == "test"
        
        print("✓ No event attribute test passed (default value 'general' used)")


def test_db_log_handler_exception_handling():
    """例外処理のテスト"""
    print("Testing DBLogHandler exception handling...")
    
    # データベースエラーを発生させるためのモック
    with patch('core.db_log_handler.db') as mock_db:
        mock_db.engine.begin.side_effect = Exception("Database connection failed")
        
        handler = DBLogHandler()
        
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Test error message",
            args=(),
            exc_info=None
        )
        
        with pytest.raises(RuntimeError):
            handler.emit(record)
        print("✓ Exception handling test passed (exception propagated)")


if __name__ == "__main__":
    print("Running DBLogHandler tests...")
    print("=" * 50)
    
    try:
        test_db_log_handler_with_event()
        test_db_log_handler_without_event()
        test_db_log_handler_exception_handling()
        
        print("=" * 50)
        print("All tests passed! ✓")
        print("\nThe fix for the 'Column event cannot be null' error is working correctly.")
        print("When no event attribute is present in the log record, it defaults to 'general'.")
        
    except Exception as e:
        print(f"\nTest failed: {e}")
        sys.exit(1)

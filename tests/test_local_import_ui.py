"""
ローカルインポートのSession Detail UI テスト
"""

import os
import tempfile
from pathlib import Path

import pytest

from webapp import create_app
from webapp.extensions import db
from core.tasks.local_import import local_import_task


@pytest.fixture
def app():
    """テスト用のFlaskアプリケーションを作成"""
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test.db"
        import_dir = Path(temp_dir) / "import"
        originals_dir = Path(temp_dir) / "originals"
        
        import_dir.mkdir()
        originals_dir.mkdir()
        
        # テストファイル作成
        (import_dir / "test_file.jpg").write_bytes(b"fake image data")
        
        # 環境変数設定
        test_config = {
            'TESTING': True,
            'SECRET_KEY': 'test-secret-key',
            'DATABASE_URI': f'sqlite:///{db_path}',
            'LOCAL_IMPORT_DIR': str(import_dir),
            'FPV_NAS_ORIGINALS_DIR': str(originals_dir),
            'FPV_TMP_DIR': str(temp_dir),
            'SQLALCHEMY_ENGINE_OPTIONS': {},
        }
        
        # 環境変数を一時的に設定
        old_env = {}
        for key, value in test_config.items():
            old_env[key] = os.environ.get(key)
            os.environ[key] = str(value)
        
        try:
            app = create_app()
            app.config.update(test_config)
            
            with app.app_context():
                db.create_all()
                yield app
                
        finally:
            # 環境変数を復元
            for key, old_value in old_env.items():
                if old_value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = old_value


class TestSessionDetailAPI:
    """Session Detail API のテスト"""
    
    def test_picker_sessions_list_includes_local_import(self, app):
        """セッション一覧にローカルインポートセッションが含まれることをテスト"""
        client = app.test_client()
        
        with client.session_transaction() as sess:
            sess['_user_id'] = '1'
            sess['_fresh'] = True
        
        with app.app_context():
            # ローカルインポート実行
            result = local_import_task()
            session_id = result['session_id']
        
        # セッション一覧API呼び出し
        response = client.get('/api/picker/sessions?pageSize=50')
        assert response.status_code == 200
        
        data = response.get_json()
        assert 'sessions' in data
        
        # ローカルインポートセッションが含まれていることを確認
        local_sessions = [s for s in data['sessions'] if s['sessionId'] and s['sessionId'].startswith('local_import_')]
        assert len(local_sessions) > 0
        
        # 最新のローカルインポートセッションの確認
        latest_local = next(s for s in local_sessions if s['sessionId'] == session_id)
        assert latest_local['status'] == 'imported'
        assert latest_local['selectedCount'] == 1
        assert latest_local['accountId'] is None
        assert 'imported' in latest_local['counts']
        assert latest_local['counts']['imported'] == 1
    
    def test_session_status_api_for_local_import(self, app):
        """ローカルインポートセッションの状態API テスト"""
        client = app.test_client()
        
        with client.session_transaction() as sess:
            sess['_user_id'] = '1'
            sess['_fresh'] = True
        
        with app.app_context():
            # ローカルインポート実行
            result = local_import_task()
            session_id = result['session_id']
        
        # セッション状態API呼び出し
        response = client.get(f'/api/picker/session/{session_id}')
        assert response.status_code == 200
        
        data = response.get_json()
        assert data['sessionId'] == session_id
        assert data['status'] == 'imported'
        assert data['selectedCount'] == 1
        # ローカルインポートセッションの特徴
        assert data.get('pickerUri') is None
        assert data.get('expireTime') is None
    
    def test_session_selections_api_for_local_import(self, app):
        """ローカルインポートセッションの選択一覧API テスト"""
        client = app.test_client()
        
        with client.session_transaction() as sess:
            sess['_user_id'] = '1'
            sess['_fresh'] = True
        
        with app.app_context():
            # ローカルインポート実行
            result = local_import_task()
            session_id = result['session_id']
        
        # セッション選択一覧API呼び出し
        response = client.get(f'/api/picker/session/{session_id}/selections')
        assert response.status_code == 200
        
        data = response.get_json()
        assert 'selections' in data
        assert 'counts' in data
        assert len(data['selections']) == 1
        
        # 選択の詳細確認
        selection = data['selections'][0]
        assert selection['googleMediaId'] is None
        assert selection['filename'] == 'test_file.jpg'
        assert selection['status'] == 'imported'
        assert selection['attempts'] >= 0
        assert selection['enqueuedAt'] is not None
        assert selection['startedAt'] is not None
        assert selection['finishedAt'] is not None
        assert selection['error'] is None
        
        # カウント確認
        assert data['counts']['imported'] == 1
    
    def test_session_import_api_blocked_for_local_import(self, app):
        """ローカルインポートセッションでインポートAPIがブロックされることをテスト"""
        client = app.test_client()
        
        with client.session_transaction() as sess:
            sess['_user_id'] = '1'
            sess['_fresh'] = True
        
        with app.app_context():
            # ローカルインポート実行
            result = local_import_task()
            session_id = result['session_id']
        
        # インポートAPI呼び出し（ローカルインポートセッションでは無効）
        response = client.post(f'/api/picker/session/{session_id}/import')
        
        # ローカルインポートセッションでは特別な処理が必要
        # 実装によっては適切なエラーレスポンスが返される
        assert response.status_code in [400, 409, 422]


class TestSessionDetailUI:
    """Session Detail UI のテスト"""
    
    def test_session_detail_page_renders(self, app):
        """セッション詳細ページが正しくレンダリングされることをテスト"""
        client = app.test_client()
        
        with client.session_transaction() as sess:
            sess['_user_id'] = '1'
            sess['_fresh'] = True
        
        with app.app_context():
            # ローカルインポート実行
            result = local_import_task()
            session_id = result['session_id']
        
        # セッション詳細ページ呼び出し
        response = client.get(f'/photo-view?session_id={session_id}')
        assert response.status_code == 200
        
        html = response.get_data(as_text=True)
        
        # 必要なHTML要素が含まれていることを確認
        assert 'Session Details' in html
        assert 'btn-import-start' in html
        assert 'selection-body' in html
        assert 'selection-counts' in html
        assert session_id in html or 'data-picker-session-id' in html
    
    def test_home_page_shows_local_import_sessions(self, app):
        """ホームページにローカルインポートセッションが表示されることをテスト"""
        client = app.test_client()
        
        with client.session_transaction() as sess:
            sess['_user_id'] = '1'
            sess['_fresh'] = True
        
        with app.app_context():
            # ローカルインポート実行
            result = local_import_task()
            session_id = result['session_id']
        
        # ホームページ呼び出し
        response = client.get('/photo-view')
        assert response.status_code == 200
        
        html = response.get_data(as_text=True)
        
        # セッション一覧テーブルが含まれていることを確認
        assert 'sessions-body' in html
        assert 'All Picker Sessions' in html
        assert 'local-import-btn' in html  # ローカルインポートボタン


class TestLocalImportIntegration:
    """ローカルインポート統合テスト"""
    
    def test_full_local_import_workflow(self, app):
        """完全なローカルインポートワークフローのテスト"""
        client = app.test_client()
        
        with client.session_transaction() as sess:
            sess['_user_id'] = '1'
            sess['_fresh'] = True
        
        # 1. 初期状態確認
        response = client.get('/api/sync/local-import/status')
        assert response.status_code == 200
        status_data = response.get_json()
        assert status_data['status']['pending_files'] == 1
        
        # 2. ローカルインポート実行
        with app.app_context():
            result = local_import_task()
            session_id = result['session_id']
            assert result['ok'] is True
            assert result['success'] == 1
        
        # 3. セッション一覧で確認
        response = client.get('/api/picker/sessions?pageSize=50')
        assert response.status_code == 200
        sessions_data = response.get_json()
        
        local_session = next(
            s for s in sessions_data['sessions'] 
            if s['sessionId'] == session_id
        )
        assert local_session['status'] == 'imported'
        assert local_session['selectedCount'] == 1
        
        # 4. セッション詳細で確認
        response = client.get(f'/api/picker/session/{session_id}/selections')
        assert response.status_code == 200
        selections_data = response.get_json()
        
        assert len(selections_data['selections']) == 1
        selection = selections_data['selections'][0]
        assert selection['filename'] == 'test_file.jpg'
        assert selection['status'] == 'imported'
        assert selection['googleMediaId'] is None
        
        # 5. 状態確認（取り込み済みなのでファイル数は0）
        response = client.get('/api/sync/local-import/status')
        assert response.status_code == 200
        status_data = response.get_json()
        assert status_data['status']['pending_files'] == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

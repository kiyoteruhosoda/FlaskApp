"""
ローカルインポートのSession Detail UI テスト
"""

import importlib
import io
import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

import webapp.config as config_module
from webapp import create_app
from webapp.extensions import db
from core.models.picker_session import PickerSession
from core.models.photo_models import PickerSelection
from core.models.log import Log
from core.tasks import local_import as local_import_module


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
            importlib.reload(config_module)
            importlib.reload(local_import_module)
            app = create_app()
            app.config.update(test_config)

            with app.app_context():
                logger_obj = getattr(local_import_module, "logger", None)
                if logger_obj is not None:
                    for handler in getattr(logger_obj, "handlers", []):
                        bind = getattr(handler, "bind_to_app", None)
                        if callable(bind):
                            bind(app)
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
            result = local_import_module.local_import_task()
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
            result = local_import_module.local_import_task()
            session_id = result['session_id']
        
        # セッション状態API呼び出し
        response = client.get(f'/api/picker/session/{session_id}')
        assert response.status_code == 200
        
        data = response.get_json()
        assert data['sessionId'] == session_id
        assert data['status'] == 'imported'
        assert data['selectedCount'] == 1
        assert 'stats' in data
        assert isinstance(data['stats'], dict)
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
            result = local_import_module.local_import_task()
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
        assert selection['googleMediaId'] is not None
        assert selection['googleMediaId'].startswith('local_')
        assert selection['mediaId'] is not None
        assert selection['filename'] == 'test_file.jpg'
        assert selection['status'] == 'imported'
        assert selection['attempts'] >= 0
        assert selection['enqueuedAt'] is not None
        assert selection['startedAt'] is not None
        assert selection['finishedAt'] is not None
        assert selection['error'] is None

        # カウント確認
        assert data['counts']['imported'] == 1

    def test_session_selection_error_detail_link_and_page(self, app):
        """エラー選択の詳細リンクとページが動作することを確認"""

        client = app.test_client()

        with client.session_transaction() as sess:
            sess['_user_id'] = '1'
            sess['_fresh'] = True

        with app.app_context():
            result = local_import_module.local_import_task()
            session_id = result['session_id']
            picker_session = PickerSession.query.filter_by(session_id=session_id).first()
            selection = PickerSelection.query.filter_by(session_id=picker_session.id).first()

            selection.status = 'failed'
            selection.error_msg = 'download failed'
            db.session.commit()

            log_payload = {
                "message": "Download failed",
                "_extra": {
                    "selection_id": selection.id,
                    "session_id": picker_session.session_id,
                    "error_message": "download failed",
                    "error_details": {"code": 500, "reason": "network"},
                },
            }
            db.session.add(
                Log(
                    level='ERROR',
                    event='picker.import.unexpected_error',
                    message=json.dumps(log_payload, ensure_ascii=False),
                )
            )
            db.session.commit()

        list_resp = client.get(f'/api/picker/session/{session_id}/selections')
        assert list_resp.status_code == 200
        list_payload = list_resp.get_json()
        selection_payload = list_payload['selections'][0]
        assert selection_payload['error'] == 'download failed'
        assert 'errorDetailsUrl' in selection_payload

        detail_api_resp = client.get(f"/api/picker/session/{session_id}/selections/{selection.id}/error")
        assert detail_api_resp.status_code == 200
        detail_data = detail_api_resp.get_json()
        assert detail_data['selection']['error'] == 'download failed'
        assert detail_data['logs'], 'ログ情報が含まれていること'

        detail_page_resp = client.get(selection_payload['errorDetailsUrl'])
        assert detail_page_resp.status_code == 200
        assert 'download failed' in detail_page_resp.get_data(as_text=True)

    def test_session_logs_include_status(self, app):
        """ログAPIがステータス付きのログを返すことを確認"""
        client = app.test_client()

        with client.session_transaction() as sess:
            sess['_user_id'] = '1'
            sess['_fresh'] = True

        with app.app_context():
            result = local_import_module.local_import_task()
            session_id = result['session_id']

        response = client.get(f'/api/picker/session/{session_id}/logs?limit=50')
        assert response.status_code == 200

        payload = response.get_json()
        logs = payload.get('logs', [])

        assert logs, '少なくとも1件のログが返されること'
        assert all('status' in entry for entry in logs)
        assert any(entry.get('status') for entry in logs)

    def test_session_logs_include_full_file_path(self, app):
        """ログにフルパスのファイル情報が含まれることを確認"""

        client = app.test_client()

        with client.session_transaction() as sess:
            sess['_user_id'] = '1'
            sess['_fresh'] = True

        import_dir = Path(app.config['LOCAL_IMPORT_DIR'])

        # 既存ファイルをクリーンアップ
        for child in list(import_dir.iterdir()):
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                shutil.rmtree(child)

        nested_dir = import_dir / 'nested'
        nested_dir.mkdir(parents=True, exist_ok=True)
        target_file = nested_dir / 'full_path_test.jpg'
        target_file.write_bytes(b'log-path-test')

        with app.app_context():
            result = local_import_module.local_import_task()
            session_id = result['session_id']

        target_path_str = str(target_file)

        detail_entry = next(
            (detail for detail in result['details'] if detail.get('file') == target_path_str),
            None,
        )
        assert detail_entry is not None, '結果詳細に対象ファイルが含まれていること'
        assert detail_entry.get('basename') == target_file.name

        response = client.get(f'/api/picker/session/{session_id}/logs?limit=50')
        assert response.status_code == 200

        payload = response.get_json()
        logs = payload.get('logs', [])

        success_entries = [
            entry for entry in logs if entry.get('event') == 'local_import.file.processed_success'
        ]
        assert success_entries, '成功ログが少なくとも1件含まれていること'

        matched_entry = next(
            (entry for entry in success_entries if entry.get('details', {}).get('file') == target_path_str),
            None,
        )
        assert matched_entry is not None, 'ログにフルパスが含まれていること'
        log_details = matched_entry.get('details', {})
        assert log_details.get('file_path') == target_path_str
        assert log_details.get('basename') == target_file.name
    
    def test_session_import_api_blocked_for_local_import(self, app):
        """ローカルインポートセッションでインポートAPIがブロックされることをテスト"""
        client = app.test_client()

        with client.session_transaction() as sess:
            sess['_user_id'] = '1'
            sess['_fresh'] = True
        
        with app.app_context():
            # ローカルインポート実行
            result = local_import_module.local_import_task()
            session_id = result['session_id']
        
        # インポートAPI呼び出し（ローカルインポートセッションでは無効）
        response = client.post(f'/api/picker/session/{session_id}/import')
        
        # ローカルインポートセッションでは特別な処理が必要
        # 実装によっては適切なエラーレスポンスが返される
        assert response.status_code in [400, 409, 422]

    def test_stop_local_import_api_marks_session(self, app):
        """停止APIが保留中のアイテムをスキップしセッションを更新することをテスト"""

        client = app.test_client()

        admin_user = type('AdminUser', (), {
            'is_authenticated': True,
            'has_role': lambda self, role: role == 'admin',
            'can': lambda self, perm: True
        })()

        with patch('flask_login.utils._get_user', return_value=admin_user):
            with app.app_context():
                session = PickerSession(
                    session_id='local_import_manual',
                    account_id=None,
                    status='processing',
                    selected_count=0,
                )
                db.session.add(session)
                db.session.commit()

                stats = {
                    'celery_task_id': 'fake-task',
                    'stage': 'processing',
                }
                session.set_stats(stats)
                db.session.commit()

                pending = PickerSelection(session_id=session.id, status='pending')
                enqueued = PickerSelection(session_id=session.id, status='enqueued')
                imported = PickerSelection(session_id=session.id, status='imported', finished_at=datetime.now(timezone.utc))
                db.session.add_all([pending, enqueued, imported])
                db.session.commit()

            with patch('cli.src.celery.celery_app.celery.control.revoke') as mock_revoke:
                response = client.post('/api/sync/local-import/local_import_manual/stop')

            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
            assert data['session_id'] == 'local_import_manual'
            assert data['counts']['pending'] == 0
            assert data['counts']['skipped'] >= 2

            with app.app_context():
                updated = PickerSession.query.filter_by(session_id='local_import_manual').first()
                assert updated is not None
                assert updated.status == 'canceled'
                stats = updated.stats()
                assert stats.get('cancel_requested') is True
                skipped_total = PickerSelection.query.filter_by(session_id=updated.id, status='skipped').count()
                assert skipped_total >= 2

            mock_revoke.assert_called_once_with('fake-task', terminate=False)

    def test_session_logs_api_returns_zip_events(self, app):
        """ZIP展開ログがAPI経由で取得できることを確認"""

        client = app.test_client()

        with client.session_transaction() as sess:
            sess['_user_id'] = '1'
            sess['_fresh'] = True

        import_dir = Path(app.config['LOCAL_IMPORT_DIR'])
        zip_path = import_dir / "bundle.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("images/inside.jpg", b"fake image data")

        with app.app_context():
            result = local_import_module.local_import_task()
            session_id = result['session_id']

        response = client.get(f'/api/picker/session/{session_id}/logs?limit=20')
        assert response.status_code == 200

        data = response.get_json()
        assert 'logs' in data

        events = [entry.get('event') for entry in data['logs']]
        assert any(event == 'local_import.zip.extracted' for event in events)

        extracted_entries = [entry for entry in data['logs'] if entry.get('event') == 'local_import.zip.extracted']
        assert extracted_entries, 'expected at least one zip extraction log entry'

        details = extracted_entries[-1].get('details', {})
        assert 'zip_path' in details

    def test_session_logs_download_returns_zip_archive(self, app):
        """ログダウンロードAPIでZIPファイルが取得できることを確認"""

        client = app.test_client()

        with client.session_transaction() as sess:
            sess['_user_id'] = '1'
            sess['_fresh'] = True

        with app.app_context():
            result = local_import_module.local_import_task()
            session_id = result['session_id']

        response = client.get(f'/api/picker/session/{session_id}/logs/download')
        assert response.status_code == 200
        assert response.headers['Content-Type'].startswith('application/zip')

        archive_data = io.BytesIO(response.data)
        with zipfile.ZipFile(archive_data, 'r') as archive:
            namelist = archive.namelist()
            assert 'logs.jsonl' in namelist
            assert 'metadata.json' in namelist

            logs_content = archive.read('logs.jsonl').decode('utf-8').strip()
            assert logs_content, 'logs.jsonl should not be empty'

            metadata = json.loads(archive.read('metadata.json').decode('utf-8'))
            assert metadata.get('session_id') == session_id


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
            result = local_import_module.local_import_task()
            session_id = result['session_id']
        
        # セッション詳細ページ呼び出し
        response = client.get(f'/photo_view?session_id={session_id}')
        assert response.status_code == 200
        
        html = response.get_data(as_text=True)

        # 必要なHTML要素が含まれていることを確認
        assert 'Session Details' in html
        assert 'btn-import-start' in html
        assert 'btn-local-import-stop' in html
        assert 'local-import-status' in html
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
            result = local_import_module.local_import_task()
            session_id = result['session_id']
        
        # ホームページ呼び出し
        response = client.get('/photo_view')
        assert response.status_code == 200
        
        html = response.get_data(as_text=True)

        # セッション一覧テーブルが含まれていることを確認
        assert 'sessions-body' in html
        assert 'All Picker Sessions' in html
        assert 'local-import-btn' in html  # ローカルインポートボタン
        assert 'Stop Local Import' in html


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
            result = local_import_module.local_import_task()
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
        assert selection['googleMediaId'] is not None
        assert selection['mediaId'] is not None
        
        # 5. 状態確認（取り込み済みなのでファイル数は0）
        response = client.get('/api/sync/local-import/status')
        assert response.status_code == 200
        status_data = response.get_json()
        assert status_data['status']['pending_files'] == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

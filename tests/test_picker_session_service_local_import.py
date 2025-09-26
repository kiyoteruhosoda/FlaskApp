"""
PickerSessionServiceのローカルインポート対応追加テスト
"""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
import os

import pytest

from webapp import create_app
from webapp.extensions import db
from webapp.api.picker_session_service import PickerSessionService
from webapp.api.pagination import PaginationParams
from core.models.picker_session import PickerSession
from core.models.google_account import GoogleAccount
from core.models.photo_models import PickerSelection
from core.models.log import Log
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


@pytest.fixture
def local_import_session(app):
    """ローカルインポートセッションを作成"""
    import_dir = Path(app.config['LOCAL_IMPORT_DIR'])
    
    # テストファイル作成
    (import_dir / "test_image.jpg").write_bytes(b"fake image data")
    (import_dir / "test_video.mp4").write_bytes(b"fake video data")
    
    with app.app_context():
        result = local_import_task()
        session_id = result['session_id']
        session = PickerSession.query.filter_by(session_id=session_id).first()
        return session


class TestPickerSessionServiceLocalImport:
    """PickerSessionServiceのローカルインポート対応テスト"""
    
    def test_resolve_local_import_session_identifier(self, app, local_import_session):
        """ローカルインポートセッションIDの解決テスト"""
        with app.app_context():
            session_id = local_import_session.session_id
            
            # セッションIDで解決
            resolved = PickerSessionService.resolve_session_identifier(session_id)
            assert resolved is not None
            assert resolved.id == local_import_session.id
            assert resolved.session_id == session_id
            assert resolved.account_id is None
    
    def test_status_for_local_import_session(self, app, local_import_session):
        """ローカルインポートセッションのステータス取得テスト"""
        with app.app_context():
            status = PickerSessionService.status(local_import_session)

            assert status['status'] == 'imported'
            assert status['sessionId'] == local_import_session.session_id
            assert status['selectedCount'] == 2
            assert status['pickerUri'] is None
            assert status['expireTime'] is None
            assert status['pollingConfig'] is None
            assert status['pickingConfig'] is None
            assert status['mediaItemsSet'] is None
            assert 'stats' in status
            assert isinstance(status['stats'], dict)

    def test_status_reverts_to_processing_when_pending_items_exist(self, app):
        """選択が進行中の場合はステータスが processing に戻る"""
        from webapp.extensions import db
        with app.app_context():
            ps = PickerSession(
                session_id="local_import_pending",
                status="imported",
                account_id=None,
            )
            db.session.add(ps)
            db.session.commit()

            running = PickerSelection(session_id=ps.id, status='running')
            finished = PickerSelection(session_id=ps.id, status='imported')
            db.session.add_all([running, finished])
            db.session.commit()

            result = PickerSessionService.status(ps)

            db.session.refresh(ps)
            assert ps.status == 'processing'
            assert result['status'] == 'processing'
            assert result['counts']['running'] == 1

    def test_status_uses_expanding_stage_for_display(self, app):
        """ローカルインポートのstageがexpandingのときは表示ステータスもexpandingになる"""

        from webapp.extensions import db

        with app.app_context():
            ps = PickerSession(
                session_id="local_import_stage_case",
                status="processing",
                account_id=None,
            )
            db.session.add(ps)
            db.session.commit()

            ps.set_stats({"stage": "expanding"})
            db.session.commit()

            result = PickerSessionService.status(ps)

            assert result['status'] == 'expanding'

    def test_normalize_selection_counts_collapses_aliases(self):
        """選択ステータスの集計がエイリアスを正規化することを確認"""
        raw_counts = {
            'dup': 1,
            'duplicates': 2,
            'FAILED': 3,
            '': 5,
            None: 4,
        }

        normalized = PickerSessionService._normalize_selection_counts(raw_counts)

        assert normalized['dup'] == 3
        assert normalized['failed'] == 3
        assert '' not in normalized
        assert 'duplicates' not in normalized
    
    def test_selection_details_for_local_import(self, app, local_import_session):
        """ローカルインポートセッションの選択詳細テスト"""
        with app.app_context():
            params = PaginationParams(page_size=10)
            details = PickerSessionService.selection_details(local_import_session, params)
            
            # 基本構造の確認
            assert 'selections' in details
            assert 'counts' in details
            assert 'pagination' in details
            
            # 選択数の確認
            assert len(details['selections']) == 2
            assert details['counts']['imported'] == 2
            
            # 各選択の詳細確認
            for selection in details['selections']:
                assert selection['googleMediaId'] is not None
                assert selection['mediaId'] is not None
                assert selection['filename'] in ['test_image.jpg', 'test_video.mp4']
                assert selection['status'] == 'imported'
                assert selection['attempts'] >= 0
                assert selection['enqueuedAt'] is not None
                assert selection['startedAt'] is not None
                assert selection['finishedAt'] is not None
                assert selection['error'] is None
            
            # ページング情報の確認
            assert details['pagination']['hasNext'] is False
            assert details['pagination']['hasPrev'] is False
    
    def test_selection_details_pagination_for_local_import(self, app):
        """ローカルインポートセッションの選択詳細ページングテスト"""
        with app.app_context():
            import_dir = Path(app.config['LOCAL_IMPORT_DIR'])

            # 複数ファイルを作成
            for i in range(5):
                (import_dir / f"test_file_{i}.jpg").write_bytes(f"fake data {i}".encode())

            # ローカルインポート実行
            result = local_import_task()
            session = PickerSession.query.filter_by(session_id=result['session_id']).first()

            # ページサイズ2でテスト
            params = PaginationParams(page_size=2)
            details = PickerSessionService.selection_details(session, params)

            assert len(details['selections']) == 2
            assert details['counts']['imported'] == 5
            assert details['pagination']['hasNext'] is True
            assert details['pagination']['hasPrev'] is False

    def test_selection_details_supports_filters(self, app):
        """選択詳細APIでステータス・キーワード絞り込みができることを確認"""
        with app.app_context():
            session = PickerSession(session_id="filter-session", status="ready", account_id=None)
            db.session.add(session)
            db.session.commit()

            selections = [
                PickerSelection(
                    session_id=session.id,
                    status='failed',
                    attempts=1,
                    local_filename='failed_photo.jpg',
                    google_media_id='gm_failed',
                ),
                PickerSelection(
                    session_id=session.id,
                    status='imported',
                    attempts=0,
                    local_filename='holiday_trip.png',
                    google_media_id='gm_imported',
                ),
                PickerSelection(
                    session_id=session.id,
                    status='pending',
                    attempts=0,
                    local_filename='todo_image.mov',
                    google_media_id='gm_pending',
                ),
            ]
            for selection in selections:
                db.session.add(selection)
            db.session.commit()

            failed_params = PaginationParams(page_size=10)
            failed_only = PickerSessionService.selection_details(
                session,
                failed_params,
                status_filters=['failed'],
            )

            assert len(failed_only['selections']) == 1
            assert failed_only['selections'][0]['status'] == 'failed'
            assert failed_only['selections'][0]['filename'] == 'failed_photo.jpg'
            assert failed_only['counts']['failed'] == 1
            assert failed_only['counts']['imported'] == 1

            search_params = PaginationParams(page_size=10)
            search_only = PickerSessionService.selection_details(
                session,
                search_params,
                search_term='holiday',
            )

            assert len(search_only['selections']) == 1
            assert search_only['selections'][0]['status'] == 'imported'
            assert search_only['selections'][0]['filename'] == 'holiday_trip.png'
            # countsは全体の集計を返すことを確認
            assert search_only['counts']['failed'] == 1
            assert search_only['counts']['pending'] == 1

    def test_selection_error_payload_includes_logs(self, app):
        """selection_error_payloadが関連ログを返すことを確認"""

        with app.app_context():
            session = PickerSession(session_id="error_session_test", status="failed", account_id=None)
            db.session.add(session)
            db.session.commit()

            selection = PickerSelection(
                session_id=session.id,
                status='failed',
                attempts=3,
                error_msg='network timeout',
                google_media_id='gm_test'
            )
            db.session.add(selection)
            db.session.commit()

            log_payload = {
                "message": "Picker import failed",
                "_extra": {
                    "selection_id": selection.id,
                    "session_id": session.session_id,
                    "error_message": "network timeout",
                    "error_details": {"reason": "timeout", "retryable": False},
                },
            }
            log_entry = Log(
                level='ERROR',
                event='picker.import.unexpected_error',
                message=json.dumps(log_payload, ensure_ascii=False),
            )
            db.session.add(log_entry)
            db.session.commit()

            payload = PickerSessionService.selection_error_payload(session, selection.id)

            assert payload is not None
            assert payload['selection']['id'] == selection.id
            assert payload['selection']['error'] == 'network timeout'
            assert payload['session']['sessionId'] == session.session_id
            assert payload['logs'], '少なくとも1件のログが返されること'

            first_log = payload['logs'][0]
            assert first_log['event'] == 'picker.import.unexpected_error'
            assert first_log['extra']['selection_id'] == selection.id
            assert first_log['errorDetails']['reason'] == 'timeout'

    def test_selection_details_with_mixed_statuses(self, app):
        """異なるステータスが混在するローカルインポートセッションのテスト"""
        with app.app_context():
            import_dir = Path(app.config['LOCAL_IMPORT_DIR'])

            # 正常ファイル
            (import_dir / "good_file.jpg").write_bytes(b"good data")
            
            # 空ファイル（エラーになる可能性）
            (import_dir / "empty_file.jpg").write_bytes(b"")
            
            # ローカルインポート実行
            result = local_import_task()
            session = PickerSession.query.filter_by(session_id=result['session_id']).first()
            
            details = PickerSessionService.selection_details(session)

            # 結果の確認
            assert len(details['selections']) >= 1
            total_count = sum(details['counts'].values())
            assert total_count >= 1

    def test_reimport_after_deletion_creates_new_media(self, app):
        """削除済みメディアの再取り込みが新規レコードになることを確認"""
        from webapp.extensions import db
        from core.models.photo_models import Media, PickerSelection

        with app.app_context():
            import_dir = Path(app.config['LOCAL_IMPORT_DIR'])
            originals_dir = Path(app.config['FPV_NAS_ORIGINALS_DIR'])

            file_path = import_dir / "dup.jpg"
            data = b"duplicate content"
            file_path.write_bytes(data)

            first_result = local_import_task()
            first_session = PickerSession.query.filter_by(session_id=first_result['session_id']).first()
            assert first_session is not None

            original_media = Media.query.one()
            original_hash = original_media.hash_sha256
            original_media.is_deleted = True
            db.session.commit()

            source_path = originals_dir / original_media.local_rel_path
            assert source_path.exists()
            second_file = import_dir / "dup_again.jpg"
            second_file.write_bytes(source_path.read_bytes())

            second_result = local_import_task()
            second_session = PickerSession.query.filter_by(session_id=second_result['session_id']).first()
            assert second_session is not None

            active_media = Media.query.filter_by(is_deleted=False).all()
            assert len(active_media) == 1
            assert Media.query.count() == 2
            assert active_media[0].hash_sha256 == original_hash

            selections = PickerSelection.query.filter_by(session_id=second_session.id).all()
            assert len(selections) == 1
            assert selections[0].status == 'imported'

    def test_error_status_with_only_duplicates_becomes_imported(self, app):
        """重複のみのセッションはエラーではなく imported として扱われる"""
        with app.app_context():
            ps = PickerSession(
                account_id=1,
                session_id="picker_sessions/dup_only",
                status="error",
            )
            db.session.add(ps)
            db.session.commit()

            dup_selection = PickerSelection(session_id=ps.id, status='dup')
            db.session.add(dup_selection)
            db.session.commit()

            params = PaginationParams(page_size=10)
            details = PickerSessionService.selection_details(ps, params)

            db.session.refresh(ps)
            assert ps.status == 'imported'
            assert details['counts'].get('dup') == 1

    def test_status_prefers_counts_over_remote_poll(self, app, monkeypatch):
        """PickerSessionService.status should not call remote API when local counts exist."""
        with app.app_context():
            account = GoogleAccount(
                email='dup@example.com',
                scopes='',
                oauth_token_json=None,
            )
            db.session.add(account)
            db.session.commit()

            ps = PickerSession(
                account_id=account.id,
                session_id='picker_sessions/dup_check',
                status='error',
            )
            db.session.add(ps)
            db.session.commit()

            db.session.add(PickerSelection(session_id=ps.id, status='dup'))
            db.session.commit()

            def fail_refresh(_account):
                raise AssertionError('refresh_google_token should not run when counts are available')

            monkeypatch.setattr('webapp.api.picker_session_service.refresh_google_token', fail_refresh)

            result = PickerSessionService.status(ps)

            db.session.refresh(ps)
            assert ps.status == 'imported'
            assert result['status'] == 'imported'
            assert result['selectedCount'] == 1
            assert result['counts'].get('dup') == 1

    def test_local_import_task_handles_cancellation(self, app, monkeypatch):
        """キャンセル要求時にタスクが中断されステータスが更新されることを検証"""

        with app.app_context():
            import_dir = Path(app.config['LOCAL_IMPORT_DIR'])
            for i in range(3):
                (import_dir / f'cancel_test_{i}.jpg').write_bytes(f'fake data {i}'.encode('utf-8'))

            from core.tasks import local_import as local_import_module

            original_import = local_import_module.import_single_file

            def fake_import(file_path, import_dir, originals_dir, *, session_id=None):
                result = original_import(file_path, import_dir, originals_dir, session_id=session_id)

                if session_id and not getattr(fake_import, 'triggered', False):
                    fake_import.triggered = True
                    session = PickerSession.query.filter_by(session_id=session_id).first()
                    assert session is not None

                    stats = session.stats() if hasattr(session, 'stats') else {}
                    if not isinstance(stats, dict):
                        stats = {}
                    stats['cancel_requested'] = True
                    stats['stage'] = 'canceling'
                    session.set_stats(stats)
                    session.status = 'canceled'

                    now = datetime.now(timezone.utc)
                    pending = PickerSelection.query.filter(
                        PickerSelection.session_id == session.id,
                        PickerSelection.status.in_(('pending', 'enqueued')),
                    ).all()
                    for sel in pending:
                        sel.status = 'skipped'
                        sel.finished_at = now
                    db.session.commit()

                return result

            fake_import.triggered = False
            monkeypatch.setattr(local_import_module, 'import_single_file', fake_import)

            result = local_import_module.local_import_task()

            assert result['canceled'] is True

            session = PickerSession.query.filter_by(session_id=result['session_id']).first()
            assert session is not None
            assert session.status == 'canceled'

            stats = session.stats()
            assert stats.get('stage') == 'canceled'
            assert stats.get('cancel_requested') is False

            counts = {
                status: count for status, count in db.session.query(
                    PickerSelection.status,
                    db.func.count(PickerSelection.id)
                )
                .filter(PickerSelection.session_id == session.id)
                .group_by(PickerSelection.status)
            }
            assert counts.get('skipped', 0) >= 1


class TestPickerSessionServiceMixedSessions:
    """通常のPickerSessionとローカルインポートセッションの混在テスト"""
    
    def test_mixed_session_types_in_list(self, app, local_import_session):
        """通常セッションとローカルインポートセッションが混在する一覧テスト"""
        with app.app_context():
            # 通常のPickerSessionを作成
            normal_session = PickerSession(
                account_id=1,
                session_id="picker_sessions/normal_uuid",
                status="ready",
                selected_count=0
            )
            db.session.add(normal_session)
            db.session.commit()
            
            # 全セッション取得
            all_sessions = PickerSession.query.all()
            
            # ローカルインポートセッションと通常セッションが含まれることを確認
            local_sessions = [s for s in all_sessions if s.account_id is None]
            normal_sessions = [s for s in all_sessions if s.account_id is not None]
            
            assert len(local_sessions) >= 1
            assert len(normal_sessions) >= 1
            
            # それぞれのセッションが正しく解決できることを確認
            for session in all_sessions:
                resolved = PickerSessionService.resolve_session_identifier(session.session_id)
                assert resolved is not None
                assert resolved.id == session.id
    
    def test_selection_details_for_different_session_types(self, app, local_import_session):
        """異なるタイプのセッションの選択詳細比較テスト"""
        with app.app_context():
            # ローカルインポートセッションの詳細
            local_details = PickerSessionService.selection_details(local_import_session)
            
            # ローカルインポートの特徴確認
            for selection in local_details['selections']:
                assert selection['googleMediaId'] is not None
                assert selection['mediaId'] is not None
                assert selection['filename'] is not None
            
            # 通常のPickerSessionを作成（選択なし）
            normal_session = PickerSession(
                account_id=1,
                session_id="picker_sessions/normal_uuid",
                status="ready",
                selected_count=0
            )
            db.session.add(normal_session)
            db.session.commit()
            
            # 通常セッションの詳細
            normal_details = PickerSessionService.selection_details(normal_session)
            
            # 通常セッションは選択なし
            assert len(normal_details['selections']) == 0
            assert normal_details['counts'] == {}


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

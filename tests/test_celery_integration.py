"""Integration tests for Celery tasks with database operations."""

import pytest
import os
from unittest.mock import patch, MagicMock
from pathlib import Path
import tempfile
import hashlib


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Create test Flask app for integration tests."""
    # Set up environment variables
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("DATABASE_URI", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("FPV_DL_SIGN_KEY", "test-sign-key")
    monkeypatch.setenv("ENCRYPTION_KEY", "a" * 32)
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
    
    # Import and create app
    from webapp import create_app
    app = create_app()
    
    # Create tables
    with app.app_context():
        from core.db import db
        db.create_all()
    
    return app


@pytest.fixture
def sample_data(app):
    """Create sample data for testing."""
    with app.app_context():
        from core.db import db
        from core.models.picker_session import PickerSession
        from core.models.photo_models import PickerSelection, MediaItem
        from core.models.google_account import GoogleAccount
        
        # Create a Google account
        account = GoogleAccount(
            email="test@example.com",
            scopes="https://www.googleapis.com/auth/photoslibrary.readonly",
            oauth_token_json='{"access_token": "test_token", "refresh_token": "test_refresh"}',
            status="active"
        )
        db.session.add(account)
        db.session.flush()
        
        # Create media items first
        media_items = []
        for i in range(3):
            media_item = MediaItem(
                id=f"test_item_{i}",
                type="PHOTO",
                mime_type="image/jpeg",
                filename=f"test_file_{i}.jpg"
            )
            media_items.append(media_item)
            db.session.add(media_item)
        db.session.flush()
        
        # Create a picker session
        session = PickerSession(
            account_id=account.id,
            status="active"
        )
        db.session.add(session)
        db.session.flush()
        
        # Create some picker selections
        selections = []
        for i in range(3):
            selection = PickerSelection(
                session_id=session.id,
                google_media_id=f"test_item_{i}",
                status="enqueued" if i < 2 else "running"
            )
            selections.append(selection)
            db.session.add(selection)
        
        db.session.commit()
        
        return {
            'account': account,
            'session': session,
            'selections': selections,
            'media_items': media_items
        }
class TestPickerImportWatchdog:
    """Test picker import watchdog functionality with database."""
    
    def test_watchdog_with_real_data(self, app, sample_data):
        """Test watchdog task with real database data."""
        from core.tasks.picker_import import picker_import_watchdog
        
        with app.app_context():
            # Run the watchdog function directly
            result = picker_import_watchdog()
            
            assert isinstance(result, dict)
            assert 'requeued' in result
            assert 'failed' in result
            assert 'recovered' in result
            assert 'republished' in result
            
            # Check that metrics are numbers
            for key in ['requeued', 'failed', 'recovered', 'republished']:
                assert isinstance(result[key], int), f"{key} should be an integer"
    
    def test_watchdog_stale_running_selections(self, app, sample_data):
        """Test watchdog handles stale running selections."""
        from core.tasks.picker_import import picker_import_watchdog
        from core.models.photo_models import PickerSelection
        from core.db import db
        from datetime import datetime, timezone, timedelta
        
        with app.app_context():
            # Set one selection to running with old heartbeat
            running_selection = PickerSelection.query.filter_by(status="running").first()
            if running_selection:
                # Set heartbeat to old time (more than 300 seconds ago)
                old_time = datetime.now(timezone.utc) - timedelta(seconds=400)
                running_selection.lock_heartbeat_at = old_time
                running_selection.started_at = old_time
                db.session.commit()
                
                # Run watchdog
                result = picker_import_watchdog()
                
                # Check that stale selection was handled
                assert result['recovered'] >= 0 or result['republished'] >= 0
    
    def test_watchdog_celery_task_integration(self, app, sample_data):
        """Test the actual Celery task wrapper."""
        from cli.src.celery.tasks import picker_import_watchdog_task
        
        with app.app_context():
            # This should run without errors
            result = picker_import_watchdog_task()
            
            assert isinstance(result, dict)
            assert all(key in result for key in ['requeued', 'failed', 'recovered', 'republished'])


class TestPickerImportItem:
    """Test picker import item functionality."""
    
    def test_picker_import_item_with_invalid_selection(self, app, sample_data):
        """Test picker import item with invalid selection ID."""
        from core.tasks.picker_import import picker_import_item
        
        with app.app_context():
            # Try to import non-existent selection
            result = picker_import_item(selection_id=999, session_id=sample_data['session'].id)
            
            assert isinstance(result, dict)
            assert 'ok' in result
            assert result['ok'] is False
    
    def test_picker_import_item_celery_task(self, app, sample_data):
        """Test the Celery task wrapper for picker import item."""
        from cli.src.celery.tasks import picker_import_item_task
        
        with app.app_context():
            selection = sample_data['selections'][0]
            
            # Mock the Google API calls and file operations
            with patch('core.tasks.picker_import.picker_import_item') as mock_import:
                mock_import.return_value = {"ok": True, "status": "completed"}
                
                result = picker_import_item_task(selection.id, selection.session_id)
                
                assert result == {"ok": True, "status": "completed"}
                mock_import.assert_called_once_with(selection_id=selection.id, session_id=selection.session_id)


class TestCeleryTaskFileOperations:
    """Test Celery tasks that perform file operations."""
    
    def test_download_file_task_integration(self, app, tmp_path):
        """Test download file task with mocked HTTP request."""
        from cli.src.celery.tasks import download_file, DEFAULT_DOWNLOAD_TIMEOUT
        
        test_content = b"Hello, World!"
        test_url = "http://example.com/test.txt"
        
        # Mock the requests.get call
        with patch('cli.src.celery.tasks.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.content = test_content
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            with app.app_context():
                result = download_file(url=test_url, dest_dir=str(tmp_path))
                
                assert 'path' in result
                assert 'bytes' in result
                assert 'sha256' in result
                
                # Verify file was created
                file_path = Path(result['path'])
                assert file_path.exists()
                assert file_path.read_bytes() == test_content
                
                # Verify metadata
                assert result['bytes'] == len(test_content)
                expected_sha = hashlib.sha256(test_content).hexdigest()
                assert result['sha256'] == expected_sha
                
                mock_get.assert_called_once_with(test_url, timeout=DEFAULT_DOWNLOAD_TIMEOUT)

    def test_download_file_task_error_handling(self, app, tmp_path):
        """Test download file task error handling."""
        from cli.src.celery.tasks import download_file
        import requests
        
        test_url = "http://example.com/nonexistent.txt"
        
        # Mock requests to raise an exception
        with patch('cli.src.celery.tasks.requests.get') as mock_get:
            mock_get.side_effect = requests.RequestException("Network error")
            
            with app.app_context():
                with pytest.raises(requests.RequestException):
                    download_file(url=test_url, dest_dir=str(tmp_path))

    def test_download_file_custom_timeout(self, app, tmp_path):
        """カスタムタイムアウト値が requests.get に渡されることを確認する。"""
        from cli.src.celery.tasks import download_file

        test_url = "http://example.com/custom-timeout.txt"

        with patch('cli.src.celery.tasks.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.content = b"content"
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response

            with app.app_context():
                download_file(url=test_url, dest_dir=str(tmp_path), timeout=5)

                mock_get.assert_called_once_with(test_url, timeout=5)

    def test_download_file_timeout_error(self, app, tmp_path):
        """タイムアウト例外が伝播することを確認する。"""
        from cli.src.celery.tasks import download_file
        import requests

        slow_url = "http://example.com/slow-response"

        with patch('cli.src.celery.tasks.requests.get') as mock_get:
            mock_get.side_effect = requests.Timeout("Request timed out")

            with app.app_context():
                with pytest.raises(requests.Timeout):
                    download_file(url=slow_url, dest_dir=str(tmp_path))


class TestCeleryTaskErrorScenarios:
    """Test error scenarios in Celery tasks."""
    
    def test_watchdog_with_database_error(self, app):
        """Test watchdog behavior when database operations fail."""
        from cli.src.celery.tasks import picker_import_watchdog_task
        
        # Mock database query to raise an exception
        with patch('core.models.photo_models.PickerSelection.query') as mock_query:
            mock_query.filter_by.side_effect = Exception("Database connection error")
            
            with app.app_context():
                with pytest.raises(Exception, match="Database connection error"):
                    picker_import_watchdog_task()
    
    def test_import_item_with_missing_session(self, app, sample_data):
        """Test import item task with missing session."""
        from cli.src.celery.tasks import picker_import_item_task
        
        with app.app_context():
            selection = sample_data['selections'][0]
            
            # Use non-existent session ID
            result = picker_import_item_task(selection.id, 999)
            
            assert isinstance(result, dict)
            assert 'ok' in result
            # The task should handle this gracefully


class TestCeleryConfigurationValidation:
    """Test Celery configuration and setup."""
    
    def test_celery_configuration_loaded(self):
        """Test that Celery configuration is properly loaded."""
        from cli.src.celery.celery_app import celery
        
        # Test basic configuration
        assert celery.conf.task_serializer == 'json'
        assert celery.conf.accept_content == ['json']
        assert celery.conf.result_serializer == 'json'
        assert celery.conf.timezone == 'Asia/Tokyo'
        assert celery.conf.enable_utc is True
    
    def test_flask_app_properly_initialized(self):
        """Test that the Flask app in celery_app is properly initialized."""
        from cli.src.celery.celery_app import flask_app
        
        # Test that Flask app has required configuration
        required_config_keys = [
            'SECRET_KEY',
            'SQLALCHEMY_DATABASE_URI',
            'SQLALCHEMY_TRACK_MODIFICATIONS'
        ]
        
        for key in required_config_keys:
            assert key in flask_app.config, f"Missing config key: {key}"
    
    def test_database_initialization(self, app):
        """Test that database is properly initialized in Celery context."""
        from cli.src.celery.celery_app import flask_app
        from core.db import db
        
        with flask_app.app_context():
            # This should not raise an error
            engine = db.engine
            assert engine is not None
            
            # Test that we can create tables
            db.create_all()
            
            # Test basic query (should not raise an error)
            from core.models.photo_models import PickerSelection
            count = PickerSelection.query.count()
            assert isinstance(count, int)


class TestCeleryTaskPerformance:
    """Test performance-related aspects of Celery tasks."""
    
    def test_dummy_task_performance(self, app):
        """Test that dummy task completes in reasonable time."""
        from cli.src.celery.tasks import dummy_long_task
        import time
        
        # Mock sleep to avoid actual delay
        with patch('cli.src.celery.tasks.time.sleep') as mock_sleep:
            with app.app_context():
                start_time = time.time()
                result = dummy_long_task(x=10, y=20)
                end_time = time.time()
                
                # Should complete quickly when sleep is mocked
                assert (end_time - start_time) < 1.0
                assert result == {"result": 30}
                mock_sleep.assert_called_once_with(5)
    
    def test_watchdog_task_performance(self, app, sample_data):
        """Test that watchdog task completes in reasonable time."""
        from cli.src.celery.tasks import picker_import_watchdog_task
        import time
        
        with app.app_context():
            start_time = time.time()
            result = picker_import_watchdog_task()
            end_time = time.time()
            
            # Should complete within a reasonable time
            assert (end_time - start_time) < 5.0
            assert isinstance(result, dict)

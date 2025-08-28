"""Test Celery application context integration."""

import pytest
import os
from unittest.mock import patch, MagicMock
from pathlib import Path


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Create test Flask app with Celery configuration."""
    # Set up environment variables
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("DATABASE_URI", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("FPV_DL_SIGN_KEY", "test-sign-key")
    monkeypatch.setenv("OAUTH_TOKEN_KEY", "a" * 32)
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
    
    # Ensure the test database directory exists
    db_path = tmp_path / "test.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Import and create app
    from webapp import create_app
    app = create_app()
    
    # Create tables
    with app.app_context():
        from core.db import db
        db.create_all()
    
    return app


@pytest.fixture
def celery_app(app):
    """Create test Celery app with Flask app context."""
    from cli.src.celery.celery_app import celery, flask_app
    
    # Ensure Celery uses the test Flask app context
    class TestContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
    
    # Temporarily replace the context task
    original_task = celery.Task
    celery.Task = TestContextTask
    
    yield celery
    
    # Restore original task
    celery.Task = original_task


class TestCeleryAppContext:
    """Test Celery tasks with Flask application context."""
    
    def test_celery_app_creation(self):
        """Test that Celery app is created correctly."""
        from cli.src.celery.celery_app import celery, flask_app
        
        assert celery is not None
        assert flask_app is not None
        assert hasattr(celery, 'Task')
    
    def test_flask_app_context_in_celery(self, app):
        """Test that Flask app context is available in Celery tasks."""
        from cli.src.celery.celery_app import celery, flask_app
        
        # Test that flask_app has the required configuration
        assert flask_app.config['SECRET_KEY'] is not None
        assert flask_app.config['SQLALCHEMY_DATABASE_URI'] is not None
    
    def test_context_task_wrapper(self, app, celery_app):
        """Test that ContextTask wrapper provides Flask app context."""
        from cli.src.celery.celery_app import ContextTask
        
        # Create a mock task that requires app context
        class MockTask(ContextTask):
            def run(self):
                from flask import current_app
                from core.db import db
                # This should not raise RuntimeError
                return current_app.config['SECRET_KEY']
        
        # Manually create and call the task
        task = MockTask()
        with app.app_context():
            result = task()
            assert result == app.config['SECRET_KEY']
    
    def test_picker_import_watchdog_task_context(self, app, celery_app):
        """Test that picker_import_watchdog_task has proper Flask context."""
        from cli.src.celery.tasks import picker_import_watchdog_task
        
        # Mock the picker_import_watchdog function to avoid actual DB operations
        with patch('cli.src.celery.tasks.picker_import_watchdog') as mock_watchdog:
            mock_watchdog.return_value = {"requeued": 0, "failed": 0, "recovered": 0, "republished": 0}
            
            # Test that the task can be called without RuntimeError
            with app.app_context():
                result = picker_import_watchdog_task()
                assert result is not None
                assert 'requeued' in result
                mock_watchdog.assert_called_once()
    
    def test_picker_import_item_task_context(self, app, celery_app):
        """Test that picker_import_item_task has proper Flask context."""
        from cli.src.celery.tasks import picker_import_item_task
        
        # Mock the picker_import_item function
        with patch('cli.src.celery.tasks.picker_import_item') as mock_import:
            mock_import.return_value = {"ok": True, "status": "completed"}
            
            # Test that the task can be called without RuntimeError
            with app.app_context():
                result = picker_import_item_task(selection_id=1, session_id=1)
                assert result is not None
                assert 'ok' in result
                mock_import.assert_called_once_with(selection_id=1, session_id=1)
    
    def test_dummy_long_task_context(self, app, celery_app):
        """Test that dummy_long_task has proper Flask context."""
        from cli.src.celery.tasks import dummy_long_task
        
        # Mock time.sleep to avoid actual delay
        with patch('cli.src.celery.tasks.time.sleep'):
            with app.app_context():
                result = dummy_long_task(x=2, y=3)
                assert result == {"result": 5}
    
    def test_download_file_task_context(self, app, celery_app, tmp_path):
        """Test that download_file task has proper Flask context."""
        from cli.src.celery.tasks import download_file
        
        # Mock the helper functions
        mock_content = b"test content"
        mock_sha = "test_sha256"
        
        with patch('cli.src.celery.tasks._download_content') as mock_download:
            with patch('cli.src.celery.tasks._save_content') as mock_save:
                mock_download.return_value = (mock_content, mock_sha)
                
                with app.app_context():
                    result = download_file(url="http://example.com/file", dest_dir=str(tmp_path))
                    
                    assert result is not None
                    assert 'path' in result
                    assert 'bytes' in result
                    assert 'sha256' in result
                    assert result['bytes'] == len(mock_content)
                    assert result['sha256'] == mock_sha
                    
                    mock_download.assert_called_once_with("http://example.com/file")
                    mock_save.assert_called_once()


class TestCeleryIntegration:
    """Test Celery integration with database operations."""
    
    def test_database_access_in_task(self, app, celery_app):
        """Test that database can be accessed within Celery tasks."""
        from core.models.photo_models import PickerSelection
        from core.db import db
        
        # Create a test function that mimics what picker_import_watchdog does
        def test_db_query():
            from flask import current_app
            with current_app.app_context():
                # This should not raise RuntimeError
                selections = PickerSelection.query.filter_by(status="running").all()
                return len(selections)
        
        # This should work without errors
        with app.app_context():
            db.create_all()  # Ensure tables exist
            count = test_db_query()
            assert isinstance(count, int)
    
    def test_celery_beat_schedule_configuration(self):
        """Test that Celery beat schedule is properly configured."""
        from cli.src.celery.celery_app import celery
        
        assert hasattr(celery.conf, 'beat_schedule')
        assert 'picker-import-watchdog' in celery.conf.beat_schedule
        
        watchdog_schedule = celery.conf.beat_schedule['picker-import-watchdog']
        assert watchdog_schedule['task'] == 'picker_import.watchdog'
        assert 'schedule' in watchdog_schedule
    
    def test_celery_task_registration(self):
        """Test that all expected tasks are registered with Celery."""
        from cli.src.celery.celery_app import celery
        
        expected_tasks = [
            'cli.src.celery.tasks.dummy_long_task',
            'cli.src.celery.tasks.download_file',
            'picker_import.item',
            'picker_import.watchdog'
        ]
        
        registered_tasks = list(celery.tasks.keys())
        
        for task_name in expected_tasks:
            assert task_name in registered_tasks, f"Task {task_name} not registered"


class TestCeleryErrorHandling:
    """Test error handling in Celery tasks."""
    
    def test_task_without_app_context_still_works(self, app, celery_app):
        """Test that tasks work even when called outside app context."""
        from cli.src.celery.tasks import dummy_long_task
        
        # Mock time.sleep to avoid actual delay
        with patch('cli.src.celery.tasks.time.sleep'):
            # This should work because ContextTask provides app context
            result = dummy_long_task(x=5, y=7)
            assert result == {"result": 12}
    
    def test_database_error_handling(self, app, celery_app):
        """Test error handling when database operations fail."""
        from cli.src.celery.tasks import picker_import_watchdog_task
        
        # Mock the underlying function to raise an exception
        with patch('cli.src.celery.tasks.picker_import_watchdog') as mock_watchdog:
            mock_watchdog.side_effect = Exception("Database error")
            
            with app.app_context():
                with pytest.raises(Exception, match="Database error"):
                    picker_import_watchdog_task()

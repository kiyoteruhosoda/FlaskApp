"""Unit tests for Celery application configuration and setup."""

import pytest
import os
from unittest.mock import patch, MagicMock


class TestCeleryAppConfiguration:
    """Test Celery application configuration."""
    
    def test_celery_app_imports(self):
        """Test that Celery app can be imported successfully."""
        from cli.src.celery.celery_app import celery, flask_app
        
        assert celery is not None
        assert flask_app is not None
    
    def test_celery_broker_configuration(self):
        """Test Celery broker configuration."""
        from cli.src.celery.celery_app import celery
        
        # Test that broker URL is set
        assert celery.conf.broker_url is not None
        assert 'redis://' in celery.conf.broker_url
    
    def test_celery_backend_configuration(self):
        """Test Celery result backend configuration."""
        from cli.src.celery.celery_app import celery
        
        # Test that result backend is set
        assert celery.conf.result_backend is not None
        assert 'redis://' in celery.conf.result_backend
    
    def test_celery_serialization_configuration(self):
        """Test Celery serialization configuration."""
        from cli.src.celery.celery_app import celery
        
        assert celery.conf.task_serializer == 'json'
        assert celery.conf.accept_content == ['json']
        assert celery.conf.result_serializer == 'json'
    
    def test_celery_timezone_configuration(self):
        """Test Celery timezone configuration."""
        from cli.src.celery.celery_app import celery, flask_app

        with flask_app.app_context():
            expected_timezone = flask_app.config.get("BABEL_DEFAULT_TIMEZONE") or 'UTC'

        assert celery.conf.timezone == expected_timezone
        assert celery.conf.enable_utc is True

    def test_create_app_applies_persisted_settings(self, monkeypatch, tmp_path):
        """Ensure Celery's Flask app loads configuration stored in the database."""
        from cli.src.celery import celery_app
        from webapp.services.system_setting_service import SystemSettingService

        persisted_key = "base64:WFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFg="
        persisted_payload = {
            "CELERY_BROKER_URL": "redis://persisted/1",
            "CELERY_RESULT_BACKEND": "redis://persisted/1",
            "ENCRYPTION_KEY": persisted_key,
        }

        monkeypatch.setenv('SECRET_KEY', 'test-secret')
        db_path = tmp_path / 'celery_app.db'
        monkeypatch.setenv('DATABASE_URI', f'sqlite:///{db_path}')

        monkeypatch.setattr(
            SystemSettingService,
            "load_application_config_payload",
            classmethod(lambda cls: dict(persisted_payload)),
        )
        monkeypatch.setattr(
            SystemSettingService,
            "load_cors_config_payload",
            classmethod(lambda cls: {}),
        )
        monkeypatch.setattr(
            SystemSettingService,
            "load_cors_config",
            classmethod(lambda cls: {"allowedOrigins": []}),
        )

        app = celery_app.create_app()

        from core.settings import settings as application_settings

        with app.app_context():
            assert app.config["CELERY_BROKER_URL"] == persisted_payload["CELERY_BROKER_URL"]
            assert app.config["CELERY_RESULT_BACKEND"] == persisted_payload["CELERY_RESULT_BACKEND"]
            assert application_settings.token_encryption_key == persisted_payload["ENCRYPTION_KEY"]

    def test_beat_schedule_configuration(self):
        """Test Celery beat schedule configuration."""
        from cli.src.celery.celery_app import celery

        assert hasattr(celery.conf, 'beat_schedule')
        assert 'picker-import-watchdog' in celery.conf.beat_schedule
        assert 'logs-cleanup' in celery.conf.beat_schedule

        watchdog_config = celery.conf.beat_schedule['picker-import-watchdog']
        assert watchdog_config['task'] == 'picker_import.watchdog'
        assert 'schedule' in watchdog_config

        logs_config = celery.conf.beat_schedule['logs-cleanup']
        assert logs_config['task'] == 'logs.cleanup'
        assert 'schedule' in logs_config
        assert logs_config.get('kwargs', {}).get('retention_days') == 365


class TestFlaskAppCreation:
    """Test Flask app creation for Celery."""
    
    @patch.dict(os.environ, {
        'SECRET_KEY': 'test-secret',
        'DATABASE_URI': 'sqlite:///test.db',
        'ENCRYPTION_KEY': 'a' * 32
    })
    def test_create_app_function(self):
        """Test Flask app creation function."""
        from cli.src.celery.celery_app import create_app
        from webapp.config import BaseApplicationSettings

        app = create_app()

        assert app is not None
        assert app.config['SECRET_KEY'] == BaseApplicationSettings.SECRET_KEY
        assert app.config['SQLALCHEMY_DATABASE_URI'] == BaseApplicationSettings.SQLALCHEMY_DATABASE_URI
    
    @patch.dict(os.environ, {
        'SECRET_KEY': 'test-secret',
        'DATABASE_URI': 'sqlite:///test.db',
        'ENCRYPTION_KEY': 'a' * 32
    })
    def test_flask_app_extensions_initialization(self):
        """Test that Flask app extensions are properly initialized."""
        from cli.src.celery.celery_app import create_app

        app = create_app()

        # Test that database is initialized
        with app.app_context():
            from core.db import db
            engine = db.engine
            assert engine is not None
    
    def test_flask_app_config_inheritance(self):
        """Test that Flask app inherits from BaseApplicationSettings class."""
        from cli.src.celery.celery_app import flask_app
        from webapp.config import BaseApplicationSettings

        # Test some basic config values that should be inherited
        assert 'SQLALCHEMY_TRACK_MODIFICATIONS' in flask_app.config
        assert flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] == BaseApplicationSettings.SQLALCHEMY_TRACK_MODIFICATIONS


class TestContextTask:
    """Test ContextTask implementation."""
    
    @patch.dict(os.environ, {
        'SECRET_KEY': 'test-secret',
        'DATABASE_URI': 'sqlite:///test.db',
        'ENCRYPTION_KEY': 'a' * 32
    })
    def test_context_task_class_exists(self):
        """Test that ContextTask class is properly defined."""
        from cli.src.celery.celery_app import ContextTask, celery
        
        # Test that ContextTask is assigned to celery.Task
        assert celery.Task == ContextTask
    
    @patch.dict(os.environ, {
        'SECRET_KEY': 'test-secret',
        'DATABASE_URI': 'sqlite:///test.db',
        'ENCRYPTION_KEY': 'a' * 32
    })
    def test_context_task_provides_app_context(self):
        """Test that ContextTask provides Flask app context."""
        from cli.src.celery.celery_app import ContextTask, flask_app
        
        # Create a test task
        class TestTask(ContextTask):
            def run(self):
                from flask import current_app
                return current_app.config['SECRET_KEY']

        # Create and call the task
        task = TestTask()
        result = task()

        assert result == flask_app.config['SECRET_KEY']
    
    @patch.dict(os.environ, {
        'SECRET_KEY': 'test-secret',
        'DATABASE_URI': 'sqlite:///test.db',
        'ENCRYPTION_KEY': 'a' * 32
    })
    def test_context_task_database_access(self):
        """Test that ContextTask allows database access."""
        from cli.src.celery.celery_app import ContextTask, flask_app
        
        # Create a test task that accesses the database
        class TestDatabaseTask(ContextTask):
            def run(self):
                from core.db import db
                from flask import current_app
                # This should not raise RuntimeError
                with current_app.app_context():
                    db.create_all()
                    return True
        
        # Create and call the task
        task = TestDatabaseTask()
        result = task()
        
        assert result is True


class TestCeleryTaskRegistration:
    """Test that Celery tasks are properly registered."""
    
    def test_tasks_are_imported(self):
        """Test that tasks module is imported and tasks are registered."""
        from cli.src.celery.celery_app import celery
        
        # Import should happen automatically, but ensure it's there
        from cli.src.celery import tasks
        
        # Check that tasks are registered
        registered_task_names = list(celery.tasks.keys())
        
        expected_tasks = [
            'cli.src.celery.tasks.dummy_long_task',
            'cli.src.celery.tasks.download_file',
            'picker_import.item',
            'picker_import.watchdog',
            'logs.cleanup'
        ]
        
        for task_name in expected_tasks:
            assert task_name in registered_task_names, f"Task {task_name} not registered"
    
    def test_task_objects_are_callable(self):
        """Test that registered task objects are callable."""
        from cli.src.celery.celery_app import celery
        
        # Test a few key tasks
        task_names = [
            'cli.src.celery.tasks.dummy_long_task',
            'picker_import.watchdog'
        ]
        
        for task_name in task_names:
            task_obj = celery.tasks.get(task_name)
            assert task_obj is not None, f"Task {task_name} not found"
            assert callable(task_obj), f"Task {task_name} is not callable"


class TestEnvironmentConfiguration:
    """Test environment variable handling."""
    
    def test_default_broker_url(self):
        """Test default broker URL when environment variable is not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove CELERY_BROKER_URL if it exists
            if 'CELERY_BROKER_URL' in os.environ:
                del os.environ['CELERY_BROKER_URL']
            
            # Re-import to get fresh configuration
            import importlib
            from cli.src.celery import celery_app
            importlib.reload(celery_app)
            
            assert 'redis://localhost:6379/0' in celery_app.celery.conf.broker_url
    
    def test_default_result_backend(self):
        """Test default result backend when environment variable is not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove CELERY_RESULT_BACKEND if it exists
            if 'CELERY_RESULT_BACKEND' in os.environ:
                del os.environ['CELERY_RESULT_BACKEND']
            
            # Re-import to get fresh configuration
            import importlib
            from cli.src.celery import celery_app
            importlib.reload(celery_app)
            
            assert 'redis://localhost:6379/0' in celery_app.celery.conf.result_backend
    
    @patch.dict(os.environ, {
        'CELERY_BROKER_URL': 'redis://custom:6379/1',
        'CELERY_RESULT_BACKEND': 'redis://custom:6379/2'
    })
    def test_custom_broker_and_backend_urls(self):
        """Test custom broker and backend URLs from environment."""
        # Re-import to get fresh configuration
        import importlib
        from cli.src.celery import celery_app
        importlib.reload(celery_app)
        
        assert 'redis://custom:6379/1' in celery_app.celery.conf.broker_url
        assert 'redis://custom:6379/2' in celery_app.celery.conf.result_backend


class TestCeleryErrorHandling:
    """Test error handling in Celery app setup."""
    
    @patch('cli.src.celery.celery_app.create_app')
    def test_flask_app_creation_failure(self, mock_create_app):
        """Test handling of Flask app creation failure."""
        mock_create_app.side_effect = Exception("Flask app creation failed")

        with pytest.raises(Exception, match="Flask app creation failed"):
            from cli.src.celery import celery_app

            celery_app.create_app()
    
    def test_celery_with_invalid_broker_url(self):
        """Test Celery behavior with invalid broker URL."""
        from celery import Celery
        
        # Create Celery with invalid broker URL
        test_celery = Celery(
            'test',
            broker='invalid://broker',
            backend='invalid://backend'
        )
        
        # Celery should create without error, but connection will fail later
        assert test_celery is not None
        assert test_celery.conf.broker_url == 'invalid://broker'


class TestCeleryModuleImports:
    """Test that all required modules can be imported."""
    
    def test_core_models_import(self):
        """Test that core models can be imported in Celery context."""
        try:
            from core.models.photo_models import PickerSelection, Media
            from core.models.picker_session import PickerSession
            from core.models.google_account import GoogleAccount
            assert True  # If we get here, imports succeeded
        except ImportError as e:
            pytest.fail(f"Failed to import core models: {e}")
    
    def test_core_tasks_import(self):
        """Test that core tasks can be imported in Celery context."""
        try:
            from core.tasks.picker_import import picker_import_watchdog, picker_import_item
            assert True  # If we get here, imports succeeded
        except ImportError as e:
            pytest.fail(f"Failed to import core tasks: {e}")
    
    def test_webapp_modules_import(self):
        """Test that webapp modules can be imported in Celery context."""
        try:
            from webapp.config import BaseApplicationSettings
            from webapp.extensions import migrate, login_manager, babel
            assert True  # If we get here, imports succeeded
        except ImportError as e:
            pytest.fail(f"Failed to import webapp modules: {e}")


class TestCeleryBeatSchedule:
    """Test Celery beat schedule functionality."""
    
    def test_beat_schedule_structure(self):
        """Test beat schedule has correct structure."""
        from cli.src.celery.celery_app import celery
        
        schedule = celery.conf.beat_schedule
        assert isinstance(schedule, dict)
        
        for task_name, config in schedule.items():
            assert 'task' in config, f"Task {task_name} missing 'task' key"
            assert 'schedule' in config, f"Task {task_name} missing 'schedule' key"
    
    def test_watchdog_schedule_timing(self):
        """Test watchdog schedule timing."""
        from cli.src.celery.celery_app import celery
        from datetime import timedelta
        
        watchdog_config = celery.conf.beat_schedule['picker-import-watchdog']
        schedule = watchdog_config['schedule']
        
        # Should be a timedelta
        assert isinstance(schedule, timedelta)
        # Should be 1 minute
        assert schedule.total_seconds() == 60

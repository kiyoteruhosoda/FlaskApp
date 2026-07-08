"""Unit tests for Celery application configuration and setup."""

import os
from datetime import timedelta
from unittest.mock import patch, MagicMock

import pytest


class TestCeleryAppConfiguration:
    """Test Celery application configuration."""

    def test_celery_app_imports(self):
        """Test that Celery app can be imported successfully."""
        from cli.src.celery.celery_app import celery

        assert celery is not None

    def test_celery_broker_configuration(self):
        """Test Celery broker configuration."""
        from cli.src.celery.celery_app import celery

        assert celery.conf.broker_url is not None
        assert "redis://" in celery.conf.broker_url

    def test_celery_backend_configuration(self):
        """Test Celery result backend configuration."""
        from cli.src.celery.celery_app import celery

        assert celery.conf.result_backend is not None
        assert "redis://" in celery.conf.result_backend

    def test_celery_serialization_configuration(self):
        """Test Celery serialization configuration."""
        from cli.src.celery.celery_app import celery

        assert celery.conf.task_serializer == "json"
        assert celery.conf.accept_content == ["json"]
        assert celery.conf.result_serializer == "json"

    def test_celery_timezone_configuration(self):
        """Test Celery timezone configuration."""
        from cli.src.celery.celery_app import celery

        assert celery.conf.timezone == "UTC"
        assert celery.conf.enable_utc is True

    def test_beat_schedule_configuration(self):
        """Test Celery beat schedule configuration."""
        from cli.src.celery.celery_app import celery

        assert hasattr(celery.conf, "beat_schedule")
        assert "picker-import-watchdog" in celery.conf.beat_schedule
        assert "logs-cleanup" in celery.conf.beat_schedule

        watchdog_config = celery.conf.beat_schedule["picker-import-watchdog"]
        assert watchdog_config["task"] == "picker_import.watchdog"
        assert "schedule" in watchdog_config

        logs_config = celery.conf.beat_schedule["logs-cleanup"]
        assert logs_config["task"] == "logs.cleanup"
        assert "schedule" in logs_config
        assert logs_config.get("kwargs", {}).get("retention_days") == 365


class TestContextTask:
    """Test ContextTask implementation."""

    def test_context_task_class_exists(self):
        """Test that ContextTask class is properly defined."""
        from cli.src.celery.celery_app import ContextTask, celery

        assert celery.Task == ContextTask


class TestCeleryTaskRegistration:
    """Test that Celery tasks are properly registered."""

    def test_tasks_are_imported(self):
        """Test that tasks module is imported and tasks are registered."""
        from cli.src.celery.celery_app import celery

        from cli.src.celery import tasks  # noqa: F401

        registered_task_names = list(celery.tasks.keys())

        expected_tasks = [
            "cli.src.celery.tasks.dummy_long_task",
            "cli.src.celery.tasks.download_file",
            "picker_import.item",
            "picker_import.watchdog",
            "logs.cleanup",
        ]

        for task_name in expected_tasks:
            assert task_name in registered_task_names, f"Task {task_name} not registered"

    def test_task_objects_are_callable(self):
        """Test that registered task objects are callable."""
        from cli.src.celery.celery_app import celery

        task_names = [
            "cli.src.celery.tasks.dummy_long_task",
            "picker_import.watchdog",
        ]

        for task_name in task_names:
            task_obj = celery.tasks.get(task_name)
            assert task_obj is not None, f"Task {task_name} not found"
            assert callable(task_obj), f"Task {task_name} is not callable"


class TestEnvironmentConfiguration:
    """Test environment variable handling."""

    def test_celery_with_invalid_broker_url(self):
        """Test Celery behavior with invalid broker URL."""
        from celery import Celery

        test_celery = Celery(
            "test",
            broker="invalid://broker",
            backend="invalid://backend",
        )

        assert test_celery is not None
        assert test_celery.conf.broker_url == "invalid://broker"


class TestCeleryModuleImports:
    """Test that all required modules can be imported."""

    def test_core_models_import(self):
        """Test that core models can be imported in Celery context."""
        try:
            from bounded_contexts.photonest.infrastructure.photo_models import PickerSelection, Media
            from bounded_contexts.picker_import.infrastructure.picker_session import PickerSession
            from shared.infrastructure.models.google_account import GoogleAccount

            assert True
        except ImportError as e:
            pytest.fail(f"Failed to import core models: {e}")

    def test_core_tasks_import(self):
        """Test that core tasks can be imported in Celery context."""
        try:
            from bounded_contexts.picker_import.tasks.picker_import import picker_import_watchdog, picker_import_item

            assert True
        except ImportError as e:
            pytest.fail(f"Failed to import core tasks: {e}")


class TestCeleryBeatSchedule:
    """Test Celery beat schedule functionality."""

    def test_beat_schedule_structure(self):
        """Test beat schedule has correct structure."""
        from cli.src.celery.celery_app import celery

        schedule = celery.conf.beat_schedule
        assert isinstance(schedule, dict)

        for task_name, config in schedule.items():
            assert "task" in config, f"Task {task_name} missing 'task' key"
            assert "schedule" in config, f"Task {task_name} missing 'schedule' key"

    def test_watchdog_schedule_timing(self):
        """Test watchdog schedule timing."""
        from cli.src.celery.celery_app import celery

        watchdog_config = celery.conf.beat_schedule["picker-import-watchdog"]
        schedule = watchdog_config["schedule"]

        assert isinstance(schedule, timedelta)
        assert schedule.total_seconds() == 60

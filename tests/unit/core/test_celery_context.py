"""Test Celery application context integration."""

import pytest
import os
from unittest.mock import patch, MagicMock
from pathlib import Path


@pytest.fixture
def celery_inst():
    """Celery インスタンスを返す。"""
    from cli.src.celery.celery_app import celery

    return celery


class TestCeleryAppContext:
    """Test Celery tasks with application context."""

    def test_celery_app_creation(self):
        """Test that Celery app is created correctly."""
        from cli.src.celery.celery_app import celery

        assert celery is not None
        assert hasattr(celery, "Task")

    def test_context_task_class_exists(self):
        """Test that ContextTask class is properly defined."""
        from cli.src.celery.celery_app import ContextTask, celery

        assert celery.Task == ContextTask

    def test_picker_import_watchdog_task_callable(self):
        """Test that picker_import_watchdog_task is callable."""
        from cli.src.celery.tasks import picker_import_watchdog_task

        with patch("cli.src.celery.tasks.picker_import_watchdog") as mock_watchdog:
            mock_watchdog.return_value = {
                "requeued": 0,
                "failed": 0,
                "recovered": 0,
                "republished": 0,
            }

            result = picker_import_watchdog_task()
            assert result is not None
            assert "requeued" in result
            mock_watchdog.assert_called_once()

    def test_picker_import_item_task_callable(self):
        """Test that picker_import_item_task is callable."""
        from cli.src.celery.tasks import picker_import_item_task

        with patch("cli.src.celery.tasks.picker_import_item") as mock_import:
            mock_import.return_value = {"ok": True, "status": "completed"}

            result = picker_import_item_task(selection_id=1, session_id=1)
            assert result is not None
            assert "ok" in result
            mock_import.assert_called_once_with(selection_id=1, session_id=1)

    def test_dummy_long_task_runs(self):
        """Test that dummy_long_task executes correctly."""
        from cli.src.celery.tasks import dummy_long_task

        with patch("cli.src.celery.tasks.time.sleep"):
            result = dummy_long_task(x=2, y=3)
            assert result == {"ok": True, "result": 5}

    def test_download_file_task_callable(self, tmp_path):
        """Test that download_file task is callable."""
        from cli.src.celery.tasks import download_file, DEFAULT_DOWNLOAD_TIMEOUT

        mock_content = b"test content"
        mock_sha = "test_sha256"

        with patch("cli.src.celery.tasks._download_content") as mock_download:
            with patch("cli.src.celery.tasks._save_content") as mock_save:
                mock_download.return_value = (mock_content, mock_sha)

                result = download_file(url="http://example.com/file", dest_dir=str(tmp_path))

                assert result is not None
                assert "path" in result
                assert "bytes" in result
                assert "sha256" in result
                assert result["bytes"] == len(mock_content)
                assert result["sha256"] == mock_sha

                mock_download.assert_called_once_with(
                    "http://example.com/file", timeout=DEFAULT_DOWNLOAD_TIMEOUT
                )
                mock_save.assert_called_once()


class TestCeleryIntegration:
    """Test Celery integration."""

    def test_celery_beat_schedule_configuration(self):
        """Test that Celery beat schedule is properly configured."""
        from cli.src.celery.celery_app import celery

        assert hasattr(celery.conf, "beat_schedule")
        assert "picker-import-watchdog" in celery.conf.beat_schedule
        assert "logs-cleanup" in celery.conf.beat_schedule

        watchdog_schedule = celery.conf.beat_schedule["picker-import-watchdog"]
        assert watchdog_schedule["task"] == "picker_import.watchdog"
        assert "schedule" in watchdog_schedule

        logs_schedule = celery.conf.beat_schedule["logs-cleanup"]
        assert logs_schedule["task"] == "logs.cleanup"
        assert "schedule" in logs_schedule

    def test_celery_task_registration(self):
        """Test that all expected tasks are registered with Celery."""
        from cli.src.celery.celery_app import celery

        expected_tasks = [
            "cli.src.celery.tasks.dummy_long_task",
            "cli.src.celery.tasks.download_file",
            "picker_import.item",
            "picker_import.watchdog",
            "logs.cleanup",
        ]

        registered_tasks = list(celery.tasks.keys())

        for task_name in expected_tasks:
            assert task_name in registered_tasks, f"Task {task_name} not registered"


class TestCeleryErrorHandling:
    """Test error handling in Celery tasks."""

    def test_task_dummy_long_task_works(self):
        """Test that dummy_long_task works correctly."""
        from cli.src.celery.tasks import dummy_long_task

        with patch("cli.src.celery.tasks.time.sleep"):
            result = dummy_long_task(x=5, y=7)
            assert result == {"ok": True, "result": 12}

    def test_database_error_handling(self):
        """Test error handling when database operations fail."""
        from cli.src.celery.tasks import picker_import_watchdog_task

        with patch("cli.src.celery.tasks.picker_import_watchdog") as mock_watchdog:
            mock_watchdog.side_effect = Exception("Database error")

            result = picker_import_watchdog_task()

        assert result["ok"] is False
        assert result["error"] == "Database error"

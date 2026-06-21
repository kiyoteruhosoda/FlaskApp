"""Test Celery logging to database."""

import sys
import os
sys.path.append('/home/kyon/myproject')

from cli.src.celery.celery_app import celery, flask_app


def test_celery_logging():
    """Test that Celery tasks can log to database."""
    with flask_app.app_context():
        # Test dummy task with error
        try:
            result = celery.send_task('cli.src.celery.tasks.dummy_long_task', args=[1, "invalid"])
            print(f"Task sent: {result.id}")
            
            # Wait for result
            result_data = result.get(timeout=10)
            print(f"Task result: {result_data}")
            
        except Exception as e:
            print(f"Error sending task: {e}")
            
        # Check if logs were written to database
        from core.db import db
        from core.models.log import Log
        
        # Get recent celery logs
        recent_logs = Log.query.filter(
            Log.event.like('%celery%')
        ).order_by(Log.created_at.desc()).limit(10).all()
        
        print(f"\nRecent Celery logs in DB ({len(recent_logs)} found):")
        for log in recent_logs:
            print(f"- {log.created_at}: {log.level} - {log.event} - {log.message}")


if __name__ == "__main__":
    test_celery_logging()

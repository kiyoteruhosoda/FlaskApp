

from webapp import create_app
import logging
from core.db_log_handler import DBLogHandler

app = create_app()

if __name__ == "__main__":
    from datetime import datetime, timezone
    with app.app_context():
        now = datetime.now(timezone.utc).isoformat()
        app.logger.info(f"Start Flask web app: wsgi.py {now}", extra={"event": "app.startup"})

    app.run(debug=True)

from celery import Celery
from flask import Flask
from webapp.config import Config
from datetime import timedelta

def make_celery(app: Flask):
    celery = Celery(
        app.import_name,
        broker="redis://localhost:6379/0",  # Broker
        backend="redis://localhost:6379/0"  # 結果を取得する場合
    )
    celery.conf.update(app.config)
    return celery

app = Flask(__name__)
app.config.from_object(Config)
celery = make_celery(app)

celery.conf.beat_schedule = {
    "picker-import-watchdog": {
        "task": "picker_import.watchdog",
        "schedule": timedelta(minutes=1),
    }
}

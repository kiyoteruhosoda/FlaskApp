import os
from dotenv import load_dotenv
from celery import Celery
from flask import Flask
from webapp.config import Config
from datetime import timedelta

# .envファイルを読み込み
load_dotenv()

def make_celery(app: Flask):
    celery = Celery(
        app.import_name,
        broker=app.config.get("broker_url", "redis://localhost:6379/0"),
        backend=app.config.get("result_backend", "redis://localhost:6379/0")
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

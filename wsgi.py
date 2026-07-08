"""WSGI エントリポイント（非推奨）。

Flask 撤廃（T11）に伴い、このファイルは廃止予定。
本番では ``uvicorn asgi:app`` / ``gunicorn asgi:app -k uvicorn.workers.UvicornWorker``
を使用すること。

後方互換のために asgi.py の FastAPI アプリを ASGI として公開する。
"""
from asgi import app  # noqa: F401


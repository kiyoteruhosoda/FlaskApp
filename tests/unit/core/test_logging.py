"""ログ関連のユニットテスト（FastAPI 移行後）。

Flask ミドルウェアに依存していたリクエストログテストは T11 移行後に FastAPI
ミドルウェアへの移行が完了次第、再実装する（ADR-0005 参照）。
現在はモデル・ユーティリティレベルのテストのみを維持する。
"""

import base64
import json
import os

import pytest


@pytest.fixture
def db_session(tmp_path):
    """テスト用 SQLite DB セッションを返す。"""
    os.environ.setdefault("SECRET_KEY", "test-secret-key")
    os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")
    os.environ.setdefault("DATABASE_URI", f"sqlite:///{tmp_path / 'test.db'}")
    os.environ.setdefault("GOOGLE_CLIENT_ID", "")
    os.environ.setdefault("GOOGLE_CLIENT_SECRET", "")
    os.environ.setdefault("ENCRYPTION_KEY", base64.urlsafe_b64encode(b"0" * 32).decode())
    os.environ.setdefault("MEDIA_DOWNLOAD_SIGNING_KEY", base64.urlsafe_b64encode(b"1" * 32).decode())
    os.environ.setdefault("ACCESS_TOKEN_ISSUER", "test")
    os.environ.setdefault("ACCESS_TOKEN_AUDIENCE", "test")

    import sqlalchemy as sa
    from sqlalchemy.orm import sessionmaker
    from shared.kernel.database.db import db

    # モデルをメタデータに登録
    import shared.infrastructure.models.log  # noqa: F401
    import shared.infrastructure.models.google_account  # noqa: F401
    import bounded_contexts.picker_import.infrastructure.picker_session  # noqa: F401
    import bounded_contexts.photonest.infrastructure.photo_models  # noqa: F401
    import bounded_contexts.totp.infrastructure.totp_models  # noqa: F401
    import bounded_contexts.wiki.infrastructure.wiki_models  # noqa: F401

    engine = sa.create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    db.metadata.create_all(engine)

    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_status_change_logged(db_session):
    """Statusフィールドの変更がログに記録されることを確認する。"""
    from shared.kernel.utils import log_status_change
    from shared.infrastructure.models.log import Log
    from shared.infrastructure.models.google_account import GoogleAccount
    from bounded_contexts.picker_import.infrastructure.picker_session import PickerSession

    gacc = GoogleAccount(email="a@example.com", scopes="scope")
    db_session.add(gacc)
    db_session.commit()

    ps = PickerSession(account_id=gacc.id)
    db_session.add(ps)
    db_session.commit()

    old = ps.status
    ps.status = "ready"
    log_status_change(ps, old, ps.status)
    db_session.commit()

    log = (
        db_session.query(Log)
        .filter_by(event="status.change")
        .order_by(Log.id.desc())
        .first()
    )
    assert log is not None
    data = json.loads(log.message)
    assert data["model"] == "PickerSession"
    assert data["to"] == "ready"

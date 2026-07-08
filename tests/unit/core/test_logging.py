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
    from bounded_contexts.certs.infrastructure.models import (  # noqa: F401
        CertificateGroupEntity, IssuedCertificateEntity, CertificatePrivateKeyEntity,
    )

    engine = sa.create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    db.metadata.create_all(engine)

    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_status_change_logged(db_session, caplog):
    """Statusフィールドの変更がログに記録されることを確認する。"""
    import logging
    from shared.kernel.utils import log_status_change
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
    with caplog.at_level(logging.INFO):
        log_status_change(ps, old, ps.status)

    assert any("status.change" in r.getMessage() or "ready" in r.getMessage() for r in caplog.records), \
        "status.change ログが記録されていません"
    # ログメッセージに遷移情報が含まれることを確認
    log_messages = [r.getMessage() for r in caplog.records]
    status_log = next((m for m in log_messages if "ready" in m), None)
    assert status_log is not None
    data = json.loads(status_log)
    assert data["model"] == "PickerSession"
    assert data["to"] == "ready"

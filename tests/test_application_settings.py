"""ApplicationSettings のユニットテスト"""

from pathlib import Path

from core.settings import ApplicationSettings


def test_defaults_are_applied_when_env_missing():
    settings = ApplicationSettings(env={})

    assert settings.celery_broker_url == "redis://localhost:6379/0"
    assert settings.celery_result_backend == "redis://localhost:6379/0"
    assert settings.backup_directory == Path("/app/data/backups")
    assert settings.tmp_directory == Path("/tmp/fpv_tmp")
    assert settings.logs_database_uri == "sqlite:///application_logs.db"
    assert settings.google_client_id == ""
    assert settings.google_client_secret == ""
    assert settings.token_encryption_key is None
    assert settings.token_encryption_key_file is None
    assert settings.transcode_crf == 20
    assert settings.service_account_signing_audiences == ()
    assert settings.access_token_issuer == "fpv-webapp"
    assert settings.access_token_audience == "fpv-webapp"


def test_environment_overrides_are_reflected():
    env = {
        "CELERY_BROKER_URL": "redis://broker/1",
        "CELERY_RESULT_BACKEND": "redis://backend/2",
        "MEDIA_BACKUP_DIRECTORY": "/data/backups",
        "MEDIA_TEMP_DIRECTORY": "/var/tmp/fpv",
        "DATABASE_URI": "sqlite:///logs.db",
        "GOOGLE_CLIENT_ID": "client",
        "GOOGLE_CLIENT_SECRET": "secret",
        "ENCRYPTION_KEY": "base64:QUJDREVGR0hJSktMTU5PUA==",
        "FPV_TRANSCODE_CRF": "24",
        "FPV_OAUTH_TOKEN_KEY_FILE": "/secrets/token.key",
        "SERVICE_ACCOUNT_SIGNING_AUDIENCE": "aud-a, aud-b, aud-c",
        "ACCESS_TOKEN_ISSUER": "issuer-x",
        "ACCESS_TOKEN_AUDIENCE": "aud-x",
    }

    settings = ApplicationSettings(env=env)

    assert settings.celery_broker_url == "redis://broker/1"
    assert settings.celery_result_backend == "redis://backend/2"
    assert settings.backup_directory == Path("/data/backups")
    assert settings.tmp_directory == Path("/var/tmp/fpv")
    assert settings.logs_database_uri == "sqlite:///logs.db"
    assert settings.google_client_id == "client"
    assert settings.google_client_secret == "secret"
    assert settings.token_encryption_key == "base64:QUJDREVGR0hJSktMTU5PUA=="
    assert settings.token_encryption_key_file == "/secrets/token.key"
    assert settings.transcode_crf == 24
    assert settings.service_account_signing_audiences == ("aud-a", "aud-b", "aud-c")
    assert settings.access_token_issuer == "issuer-x"
    assert settings.access_token_audience == "aud-x"


def test_transcode_crf_invalid_value_falls_back_to_default():
    settings = ApplicationSettings(env={"FPV_TRANSCODE_CRF": "invalid"})

    assert settings.transcode_crf == 20

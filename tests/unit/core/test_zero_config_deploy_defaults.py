"""初期設定のみ（.env 未作成・環境変数なし）でデプロイ・起動できることの回帰テスト。

要件: tar とデプロイスクリプトだけを置いた新しいホストで
``./deploy(-stg).sh <mode>`` を実行すれば、資格情報等を一切設定しなくても
起動し、初期管理者（admin@example.com / admin）で管理画面まで到達できること。
自動生成できる値はすべてデフォルト値を持つ（JWT_SECRET_KEY 等もリスクを
許容して動作優先）。既定の資格情報は開発向けであり、外部公開時は .env で
上書きする運用とする。

過去の障害: docker-compose.yml の ``${MARIADB_USER}`` 等にデフォルト値が
なく、さらに ``env_file: .env`` と ``--env-file`` が実ファイルを要求するため、
.env を用意しない限りデプロイが即失敗 or DATABASE_URI が
``mysql+pymysql://:@db:3306/?...`` に壊れていた。また web/worker/beat に
Redis 接続情報が渡らず、アプリ既定の ``redis://localhost:6379/0``
（コンテナ内では到達不能・パスワードなし）に落ちて Celery が動かなかった。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from shared.kernel.settings.system_settings_defaults import (
    DEFAULT_APPLICATION_SETTINGS,
)

ROOT = Path(__file__).resolve().parents[3]
COMPOSE_FILE = ROOT / "docker-compose.yml"
DEPLOY_SCRIPTS = (
    ROOT / "scripts" / "deploy.sh",
    ROOT / "scripts" / "deploy-stg.sh",
)

# ${VAR} / ${VAR:-default} を抽出する（$$ エスケープはコンテナ内シェル変数なので除外）
_INTERPOLATION_RE = re.compile(r"(?<!\$)\$\{([A-Za-z_][A-Za-z0-9_]*)(:?-)?")


@pytest.mark.unit
def test_compose_interpolations_all_have_defaults():
    """docker-compose.yml の全変数展開 ``${VAR}`` が ``:-`` デフォルト値を持つこと。

    デフォルトのない展開が1つでもあると、.env（または環境変数）を用意しない
    デプロイでその値が空文字になり、DATABASE_URI 破損などの形で壊れる。
    """
    text = COMPOSE_FILE.read_text(encoding="utf-8")

    missing: list[str] = []
    for match in _INTERPOLATION_RE.finditer(text):
        var, has_default = match.group(1), match.group(2)
        if not has_default:
            missing.append(var)

    assert not missing, (
        "docker-compose.yml にデフォルト値なしの変数展開があります"
        f"（.env なしのデプロイが壊れます）: {sorted(set(missing))}"
    )


@pytest.mark.unit
def test_db_credentials_defaults_match_database_uri_defaults():
    """db サービスへ渡す MARIADB_* の既定値と、web/worker/beat の DATABASE_URI に
    埋め込む既定値が一致していること（ズレると初回初期化した DB へ接続できない）。
    """
    text = COMPOSE_FILE.read_text(encoding="utf-8")

    def _defaults_of(var: str) -> set[str]:
        return set(re.findall(r"\$\{" + var + r":-([^}]*)\}", text))

    for var in ("MARIADB_USER", "MARIADB_PASSWORD", "MARIADB_DATABASE"):
        defaults = _defaults_of(var)
        assert len(defaults) == 1, (
            f"{var} の既定値が docker-compose.yml 内で一意ではありません: {defaults}"
        )


@pytest.mark.unit
def test_app_containers_receive_redis_urls_with_default_password():
    """web/worker/beat に REDIS_URL / CELERY_BROKER_URL / CELERY_RESULT_BACKEND が
    渡ること。アプリ側デフォルト（redis://localhost:6379/0）はコンテナ内では
    redis サービスへ到達できないため、compose が必ず注入する必要がある。
    """
    import yaml

    # compose の変数展開構文（${VAR:-default}）は YAML としてはただの文字列
    compose = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))

    for service in ("web", "worker", "beat"):
        env_list = compose["services"][service].get("environment", [])
        joined = "\n".join(str(e) for e in env_list)
        for key in ("REDIS_URL", "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND"):
            assert f"{key}=" in joined, (
                f"{service} サービスに {key} が注入されていません"
                "（.env なしでは Celery が localhost へ接続しようとして壊れます）"
            )
            assert "@redis:6379" in joined, (
                f"{service} の Redis 接続既定値が compose 内の redis サービスを"
                "指していません"
            )


@pytest.mark.unit
@pytest.mark.parametrize("script", DEPLOY_SCRIPTS, ids=lambda p: p.name)
def test_deploy_scripts_generate_env_file_when_missing(script: Path):
    """デプロイスクリプトが .env 不在時にテンプレートを自動生成すること。

    docker compose は ``--env-file`` と各サービスの ``env_file: .env`` の両方で
    実ファイルの存在を要求するため、生成しない限り初期設定のみのデプロイは
    「env file not found」で即失敗する。
    """
    text = script.read_text(encoding="utf-8")

    assert re.search(r"if \[ ! -f \"\$ENV_FILE\" \]", text), (
        f"{script.name} に .env 不在時の自動生成ガードがありません"
    )
    assert re.search(r"cat > \"\$ENV_FILE\"", text), (
        f"{script.name} が .env を生成していません"
    )
    # reset 時の削除パス（$BASE_DIR/db_data 等）と compose のバインドマウント先を
    # 一致させるため、生成する .env は HOST_DATA_ROOT を BASE_DIR に固定する。
    assert "HOST_DATA_ROOT=$BASE_DIR" in text, (
        f"{script.name} の生成 .env が HOST_DATA_ROOT を BASE_DIR に揃えていません"
        "（reset モードが実データと別のパスを削除する事故につながります）"
    )


@pytest.mark.unit
def test_stg_generated_env_pins_stg_specific_ports():
    """deploy-stg.sh が生成する .env は STG 固有の実値（ヘルスチェック先 8051 等）を
    固定すること。compose 既定値（8050/3307）のままだとスクリプト自身の
    HEALTH_URL（127.0.0.1:8051）と食い違い、デプロイが必ず失敗する。
    """
    text = (ROOT / "scripts" / "deploy-stg.sh").read_text(encoding="utf-8")

    health_port = re.search(r"HEALTH_URL=\"http://127\.0\.0\.1:(\d+)", text)
    assert health_port, "deploy-stg.sh に HEALTH_URL がありません"
    assert f"WEB_HOST_PORT={health_port.group(1)}" in text, (
        "deploy-stg.sh が生成する .env の WEB_HOST_PORT が HEALTH_URL の"
        "ポートと一致していません"
    )


@pytest.mark.unit
def test_builtin_secrets_have_working_defaults():
    """JWT_SECRET_KEY / SECRET_KEY は未設定でも動作するデフォルト値を持つこと
    （動作優先の方針。外部公開時の上書きは運用でカバーする）。
    """
    for key in ("JWT_SECRET_KEY", "SECRET_KEY"):
        value = DEFAULT_APPLICATION_SETTINGS.get(key)
        assert isinstance(value, str) and value.strip(), (
            f"{key} のデフォルト値がありません。未設定環境でログインが壊れます"
        )

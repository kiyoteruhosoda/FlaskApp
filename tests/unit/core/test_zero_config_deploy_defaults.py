"""初期設定のみ（.env 未作成・環境変数なし）でデプロイ・起動できることの回帰テスト。

要件: image.tar とデプロイスクリプトだけを置いた新しいホスト
（``photonest/<stg|prod>/`` ディレクトリ）で ``./scripts/deploy.sh <mode>`` を
実行すれば、資格情報等を一切設定しなくても
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
    # reset 時の削除パス（<環境dir>/mnt/db_data 等）と compose のバインドマウント先を
    # 一致させるため、生成する .env は HOST_DATA_ROOT を <環境dir>/mnt に固定する。
    assert "HOST_DATA_ROOT=$BASE_DIR/mnt" in text, (
        f"{script.name} の生成 .env が HOST_DATA_ROOT を <環境dir>/mnt に揃えていません"
        "（reset モードが実データと別のパスを削除する事故につながります）"
    )


@pytest.mark.unit
def test_deploy_script_creates_host_mount_root_before_up():
    """`docker compose up` の前に HOST_DATA_ROOT（マウントルート）を作成すること。

    init-paths コンテナが data/・db_data/ のサブディレクトリを作るが、その
    init-paths 自身が HOST_DATA_ROOT をバインドマウントする。Docker はバインド
    マウント元を自動作成しないため、mnt/ が存在しない新規デプロイでは最初の
    コンテナ起動時点で ``Bind mount failed: '<HOST_DATA_ROOT>' does not exist``
    となり、以降のコンテナが一切起動しない（ログも残らない）。
    """
    text = (ROOT / "scripts" / "deploy.sh").read_text(encoding="utf-8")

    up_index = text.index("$COMPOSE up -d")
    mkdir_pattern = re.compile(r'mkdir -p "\$HOST_DATA_ROOT"')
    match = mkdir_pattern.search(text)
    assert match is not None, (
        "deploy.sh が HOST_DATA_ROOT（マウントルート）を mkdir していません"
        "（init-paths のバインドマウントが 'does not exist' で失敗します）"
    )
    assert match.start() < up_index, (
        "HOST_DATA_ROOT の作成が 'docker compose up' より後になっています"
    )


@pytest.mark.unit
def test_deploy_script_env_file_value_strips_cr_and_whitespace():
    """.env から読む値の CR（CRLF 改行）と前後空白を除去すること。

    Windows で編集された .env は CRLF になりうる。docker compose 自身の .env
    パーサーは CRLF を許容するが、deploy.sh が grep/cut で読んで export した値は
    compose の値より優先されるため、CR が残ると HOST_DATA_ROOT 等のパスが
    ``Bind mount failed: '<path>\\r' does not exist`` という一見矛盾したエラーに
    なる（エラー表示自体も CR で行頭上書きされ判読不能になる）。
    """
    text = (ROOT / "scripts" / "deploy.sh").read_text(encoding="utf-8")

    func_match = re.search(r"env_file_value\(\)\s*\{(.*?)\n\}", text, re.DOTALL)
    assert func_match is not None, "deploy.sh に env_file_value 関数がありません"
    body = func_match.group(1)
    assert r"tr -d '\r'" in body, (
        "env_file_value が CR を除去していません（CRLF の .env で"
        "パスが壊れ、バインドマウントが失敗します）"
    )


@pytest.mark.unit
def test_deploy_script_guards_legacy_data_location():
    """旧配置（<環境dir>/db_data 直下）にデータが残っている場合、app/migrate を
    続行せず停止すること。マウントルートが <環境dir>/mnt に変わったため、
    ガードなしでは空の mnt/db_data で MariaDB が新規初期化され、既存データが
    使われない事故になる。
    """
    text = (ROOT / "scripts" / "deploy.sh").read_text(encoding="utf-8")

    assert re.search(
        r'\[ "\$MODE" != "reset" \] && \[ -d "\$BASE_DIR/db_data" \] && \[ ! -d "\$DB_PATH" \]',
        text,
    ), (
        "deploy.sh に旧配置 db_data の引き継ぎガードがありません"
        "（既存 DB を無視して空 DB を初期化する事故につながります）"
    )


@pytest.mark.unit
def test_deploy_script_includes_init_paths_in_diagnostics():
    """起動失敗時の診断対象サービスに init-paths を含めること。

    init-paths はマウントルート作成の run-once コンテナで、ここでの失敗が
    「db が起動しない」原因になる。診断ログの対象から漏れると原因追跡が困難。
    """
    text = (ROOT / "scripts" / "deploy.sh").read_text(encoding="utf-8")

    all_services_match = re.search(r"ALL_SERVICES=\(([^)]*)\)", text)
    assert all_services_match is not None, "deploy.sh に ALL_SERVICES がありません"
    assert "init-paths" in all_services_match.group(1), (
        "ALL_SERVICES に init-paths が含まれていません"
        "（バインドマウント失敗時に init-paths のログが診断に出ません）"
    )


@pytest.mark.unit
def test_deploy_script_health_url_follows_env_web_host_port():
    """HEALTH_URL は .env の WEB_HOST_PORT（未設定時は環境別デフォルト）に追従し、
    生成する .env も同じ値を固定すること。ヘルスチェック先と compose の公開
    ポートが食い違うと、正常起動していてもデプロイが必ず失敗する。
    """
    text = (ROOT / "scripts" / "deploy.sh").read_text(encoding="utf-8")

    assert 'HEALTH_URL="http://127.0.0.1:${WEB_HOST_PORT}/health/live"' in text, (
        "deploy.sh の HEALTH_URL が WEB_HOST_PORT に追従していません"
    )
    # stg=8051 / prod=8050 の環境別デフォルト
    assert re.search(r"stg\)\n\s*PROJECT=\"photonest-stg\"\n\s*DEFAULT_WEB_HOST_PORT=8051", text), (
        "deploy.sh の stg 用デフォルトポート（8051）がありません"
    )
    assert "DEFAULT_WEB_HOST_PORT=8050" in text, (
        "deploy.sh の prod 用デフォルトポート（8050）がありません"
    )
    # 生成 .env はスクリプトが解決した WEB_HOST_PORT と同じ値を書き込む
    assert "WEB_HOST_PORT=$WEB_HOST_PORT" in text, (
        "deploy.sh が生成する .env の WEB_HOST_PORT がヘルスチェック先の"
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

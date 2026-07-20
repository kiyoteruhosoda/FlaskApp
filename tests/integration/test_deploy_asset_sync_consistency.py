"""デプロイ資材の自己同期（self-sync）機構が壊れていないことを検証する回帰テスト。

過去、リポジトリではデプロイ不具合を修正済みなのに、NAS 上の
``docker-compose.yml`` の手動コピーが漏れて古いまま実行され、
同じ起動失敗（``flask db stamp head`` の Connection refused）が再発し続けた。

対策として、デプロイスクリプトがロード済みアプリイメージから
``/app/docker-compose.yml`` を取り出して常にイメージと同じ版を使う方式にした
（デプロイスクリプト自身はビルド成果物 ``dist/scripts/deploy.sh`` として
イメージと一緒に配布される）。この機構は次の 2 点が成立していないと機能しない:

1. ``.dockerignore`` が ``docker-compose.yml`` をビルドコンテキストから
   除外していないこと（除外するとイメージに焼き込まれない）。
2. デプロイスクリプトに同期処理（``sync_assets_from_image``）が存在すること。

同様に、compose の nginx サービスは設定ファイルを ``./docker/nginx/default.conf``
という相対パスでバインドマウントする。この相対パスは compose ファイルと同じ
ディレクトリを基準に解決されるため、イメージ内の
``/app/docker/nginx/default.conf`` を同じ相対位置へ取り出しておかないと、
``Bind mount failed: '.../docker/nginx/default.conf' does not exist`` で
nginx コンテナが起動しない。そのため次も検証する:

3. ``.dockerignore`` が nginx 設定をビルドコンテキストから除外していないこと。
4. デプロイスクリプトが ``/app/docker/nginx/default.conf`` を同期すること。

このテストはファイル内容を検査するだけで、Docker は使用しない。
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERIGNORE = ROOT / ".dockerignore"
DEPLOY_SCRIPTS = [
    ROOT / "scripts" / "deploy.sh",
]
NGINX_CONF = ROOT / "docker" / "nginx" / "default.conf"


def _dockerignore_patterns() -> list[str]:
    lines = DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]


def test_dockerignore_keeps_compose_in_build_context() -> None:
    """docker-compose.yml を除外するパターンが .dockerignore に無いこと。"""
    offending = [
        p
        for p in _dockerignore_patterns()
        if p in ("docker-compose.yml", "**/docker-compose*", "docker-compose*")
    ]
    assert not offending, (
        f".dockerignore が docker-compose.yml を除外しています: {offending}. "
        "デプロイスクリプトはイメージ内の /app/docker-compose.yml を取り出して使うため、"
        "除外するとデプロイ資材の自己同期が機能しなくなります。"
    )


def test_deploy_scripts_sync_assets_from_image() -> None:
    """デプロイスクリプトにイメージからの資材同期処理が存在すること。"""
    for script in DEPLOY_SCRIPTS:
        content = script.read_text(encoding="utf-8")
        assert "sync_assets_from_image" in content, (
            f"{script.name} にイメージからの資材同期処理がありません。"
        )
        assert "/app/docker-compose.yml" in content, (
            f"{script.name} がイメージ内の docker-compose.yml を参照していません。"
        )


def test_dockerignore_keeps_nginx_conf_in_build_context() -> None:
    """nginx 設定を除外するパターンが .dockerignore に無いこと。"""
    offending = [
        p
        for p in _dockerignore_patterns()
        if p
        in (
            "docker/nginx/default.conf",
            "docker/nginx/*",
            "docker/nginx",
            "**/docker/nginx/**",
            "**/*.conf",
        )
    ]
    assert not offending, (
        f".dockerignore が nginx 設定を除外しています: {offending}. "
        "デプロイスクリプトはイメージ内の /app/docker/nginx/default.conf を取り出して "
        "compose のバインドマウント元に使うため、除外すると nginx が起動しなくなります。"
    )


def test_deploy_scripts_sync_nginx_conf_from_image() -> None:
    """デプロイスクリプトがイメージ内の nginx 設定を同期すること。

    compose の nginx サービスは ``./docker/nginx/default.conf`` を相対パスで
    バインドマウントするため、compose ファイルと同じディレクトリにこのファイルを
    取り出しておかないと ``Bind mount failed`` で nginx が起動しない。
    """
    for script in DEPLOY_SCRIPTS:
        content = script.read_text(encoding="utf-8")
        assert "/app/docker/nginx/default.conf" in content, (
            f"{script.name} がイメージ内の nginx 設定を同期していません。"
            "compose の相対バインドマウント元が host 上に存在せず nginx が起動しません。"
        )


def test_compose_nginx_bind_mount_matches_synced_path() -> None:
    """compose の nginx バインドマウント元が、リポジトリ内の実ファイルと一致すること。"""
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "./docker/nginx/default.conf:/etc/nginx/conf.d/default.conf" in compose, (
        "compose の nginx 設定バインドマウントのパスが変わりました。"
        "変更する場合はデプロイスクリプトの同期先パスも合わせて更新してください。"
    )
    assert NGINX_CONF.is_file(), (
        f"{NGINX_CONF} が存在しません。compose がバインドマウントする nginx 設定は "
        "リポジトリに実在しイメージへ焼き込まれる必要があります。"
    )


def test_compose_uses_auto_assigned_network_subnet() -> None:
    """compose のネットワーク定義に固定 subnet / ipam 指定が無いこと。

    固定サブネットは同一ホストの全 Docker ネットワークで重複禁止のため、
    stg / prod 同居時に "Pool overlaps with other one on this address space" で
    ネットワーク作成に失敗する。サービス間通信はサービス名 DNS で解決しており
    固定 IP レンジへの依存は無いので、subnet は指定せず Docker の自動割当を使う。
    """
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    offending = [
        line.strip()
        for line in compose.splitlines()
        if line.strip().lstrip("- ").startswith(("subnet:", "ipam:"))
    ]
    assert not offending, (
        f"docker-compose.yml に固定サブネット指定があります: {offending}. "
        "同一ホストで stg / prod を同居させるとネットワーク作成が重複エラーで失敗するため、"
        "subnet は指定せず自動割当にしてください（docs/CHANGELOG.md 参照）。"
    )


def test_makefile_build_targets_enforce_clean_worktree() -> None:
    """Makefile の build / build-db が作業ツリー検証を前提に持つこと。

    イメージには作業ツリーがそのまま焼き込まれる（COPY . /app）ため、コミットされて
    いない変更が残ったままビルドすると、version.json のコミットと中身が一致しない
    成果物ができる。どのビルド入口（make 直接実行・scripts/.build.sh）からでも
    同じチェックを通るよう、Makefile のターゲット側で強制する。
    """
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    for target in ("build:", "build-db:"):
        line = next(
            (ln for ln in makefile.splitlines() if ln.startswith(target)), None
        )
        assert line is not None, f"Makefile に {target} ターゲットがありません。"
        assert "check-worktree" in line, (
            f"Makefile の {target} ターゲットが check-worktree に依存していません。"
            "作業ツリー検証を通らないビルド入口ができ、コミットと一致しない"
            "イメージが作られる恐れがあります。"
        )
    guard = ROOT / "scripts" / "check_worktree_clean.sh"
    assert guard.is_file(), f"{guard} が存在しません（check-worktree ターゲットの実体）。"


def test_deploy_scripts_self_sync_from_image() -> None:
    """デプロイスクリプトが自分自身もイメージから同期（自己更新→再実行）すること。

    2026-07-20 の prod デプロイで、配置済みのはずの最新 deploy.sh ではなく古い版が
    実行され、修正済みの診断出力が出ない事象が起きた（NAS 側の配置・起動経路は
    git 管理外）。compose / nginx 設定と同様に「イメージ内が唯一の出所」を
    スクリプト自身にも適用し、実行中のコピーが古い場合は置き換えて再実行する。
    """
    for script in DEPLOY_SCRIPTS:
        content = script.read_text(encoding="utf-8")
        assert "/app/scripts/deploy.sh" in content, (
            f"{script.name} が自分自身のイメージ内コピーを参照していません。"
            "古い deploy.sh が実行され続けても検出・自己修復できなくなります。"
        )
        assert "PHOTONEST_DEPLOY_REEXEC" in content, (
            f"{script.name} に自己更新後の再実行ガードがありません（無限再実行の防止）。"
        )


def test_build_remote_launcher_self_updates_and_uses_picked_deploy_script() -> None:
    """ホスト側ランチャー（build-remote.sh）が自己更新と deploy.sh の確実な差し替えを行うこと。

    deploy.sh の自己同期はランチャーが古い deploy.sh を実行し続ける経路そのものは
    直せない（新しい版が一度は実行される必要がある）。そのためランチャー自身が
    git pull 後のリポジトリ HEAD と自分の刻印バージョンを照合して自己更新し、
    PICK で必ず今回ビルドの deploy.sh を上書きしてから実行する。
    """
    launcher = ROOT / "scripts" / "build-remote.sh"
    assert launcher.is_file(), "scripts/build-remote.sh が存在しません。"
    content = launcher.read_text(encoding="utf-8")
    assert "BUILD_REMOTE_VERSION" in content, (
        "build-remote.sh にバージョン刻印（自己更新の判定基準）がありません。"
    )
    assert "RESTART REQUIRED" in content, (
        "build-remote.sh に自己更新後の再実行要求（RESTART REQUIRED / exit 2）がありません。"
    )
    assert "dist/scripts/deploy.sh" in content, (
        "build-remote.sh が PICK でビルド成果物の deploy.sh を配置していません。"
        "古い deploy.sh が実行され続ける経路が残ります。"
    )


def test_env_examples_manage_redis_password_in_one_place() -> None:
    """.env テンプレートが Redis パスワードを REDIS_PASSWORD の1箇所で管理していること。

    REDIS_URL / CELERY_BROKER_URL / CELERY_RESULT_BACKEND は docker-compose.yml が
    REDIS_PASSWORD から自動導出する。テンプレートが URL を明示させると、パスワード
    変更時に複数行の更新漏れで redis サーバーとクライアントの資格情報が食い違い、
    "invalid username-password pair" で web / worker / beat が全滅する（2026-07-20 の
    prod デプロイ失敗）。コメントアウト（外部 Redis 用の例示）は許可する。
    """
    url_keys = ("REDIS_URL=", "CELERY_BROKER_URL=", "CELERY_RESULT_BACKEND=")
    for name in (".env.example", ".env.staging.example"):
        lines = (ROOT / name).read_text(encoding="utf-8").splitlines()
        offending = [
            ln for ln in lines
            if ln.strip().startswith(url_keys)
        ]
        assert not offending, (
            f"{name} が Redis 接続 URL を明示させています: {offending}. "
            "パスワードは REDIS_PASSWORD の1箇所で管理し、URL は compose の自動導出に任せてください。"
        )
        assert any(ln.strip().startswith("REDIS_PASSWORD=") for ln in lines), (
            f"{name} に REDIS_PASSWORD がありません。"
        )

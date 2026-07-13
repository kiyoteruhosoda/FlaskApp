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

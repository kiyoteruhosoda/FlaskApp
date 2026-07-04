"""デプロイ資材の自己同期（self-sync）機構が壊れていないことを検証する回帰テスト。

過去、リポジトリではデプロイ不具合を修正済みなのに、NAS 上の
``deploy-stg.sh`` / ``docker-compose.yml`` の手動コピーが漏れて古いまま実行され、
同じ起動失敗（``flask db stamp head`` の Connection refused）が再発し続けた。

対策として、アプリイメージの tar を唯一の配布物とし、デプロイスクリプトが
ロード済みイメージから ``/app/docker-compose.yml`` と自分自身を取り出して
自己更新する方式にした。この機構は次の 2 点が成立していないと機能しない:

1. ``.dockerignore`` が ``docker-compose.yml`` をビルドコンテキストから
   除外していないこと（除外するとイメージに焼き込まれない）。
2. 両デプロイスクリプトに自己同期処理（``sync_assets_from_image``）と
   再実行ガード（``PHOTONEST_DEPLOY_SELF_UPDATED``）が存在すること。

このテストはファイル内容を検査するだけで、Docker は使用しない。
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERIGNORE = ROOT / ".dockerignore"
DEPLOY_SCRIPTS = [
    ROOT / "scripts" / "deploy.sh",
    ROOT / "scripts" / "deploy-stg.sh",
]


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
    """両デプロイスクリプトに自己同期処理と再実行ガードが存在すること。"""
    for script in DEPLOY_SCRIPTS:
        content = script.read_text(encoding="utf-8")
        assert "sync_assets_from_image" in content, (
            f"{script.name} にイメージからの資材同期処理がありません。"
        )
        assert "/app/docker-compose.yml" in content, (
            f"{script.name} がイメージ内の docker-compose.yml を参照していません。"
        )
        assert "PHOTONEST_DEPLOY_SELF_UPDATED" in content, (
            f"{script.name} に自己更新の再実行ガードがありません（無限ループ防止）。"
        )

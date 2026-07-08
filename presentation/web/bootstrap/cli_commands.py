"""Flask CLI コマンドの登録.

``create_app()`` から切り出した CLI コマンド（version / seed-master）の登録処理。
コマンド本体はマスタデータ投入やバージョン表示といった運用操作であり、アプリ
ファクトリ本体から分離して見通しを良くする。
"""

from __future__ import annotations

from flask import Flask
from shared.kernel.i18n.translation import gettext as _

from .extensions import db


def register_cli_commands(app: Flask) -> None:
    """CLI コマンドを登録"""
    import click
    from shared.infrastructure.models.user import Role, Permission

    @app.cli.command("version")
    def show_version():
        """アプリケーションのバージョン情報を表示"""
        from shared.kernel.version import get_version_info, get_version_string

        click.echo(_("=== %(app_name)s Version Information ===", app_name=_("AppName")))
        version_info = get_version_info()

        click.echo(f"Version: {get_version_string()}")
        click.echo(f"Commit Hash: {version_info['commit_hash']}")
        click.echo(f"Branch: {version_info['branch']}")
        click.echo(f"Commit Date: {version_info['commit_date']}")
        click.echo(f"Build Date: {version_info['build_date']}")

    @app.cli.command("seed-master")
    @click.option('--force', is_flag=True, help='既存データがあっても強制実行')
    def seed_master_data(force):
        """マスタデータを投入"""
        from scripts.seed_master_data import (
            seed_roles, seed_permissions, seed_role_permissions, seed_admin_user
        )

        click.echo(_("=== %(app_name)s Master Data Seeding ===", app_name=_("AppName")))

        # 既存データチェック
        if not force:
            if Role.query.first() or Permission.query.first():
                click.echo("Warning: Master data already exists. Use --force to override.")
                return

        try:
            click.echo("\n1. Seeding roles...")
            seed_roles()

            click.echo("\n2. Seeding permissions...")
            seed_permissions()

            db.session.commit()

            click.echo("\n3. Seeding role-permission relationships...")
            seed_role_permissions()

            click.echo("\n4. Seeding admin user...")
            seed_admin_user()

            db.session.commit()
            click.echo("\n=== Seeding completed successfully! ===")

        except Exception as e:
            db.session.rollback()
            click.echo(f"\n=== Seeding failed: {e} ===", err=True)
            raise click.ClickException(str(e))

    @app.cli.command("rebuild-originals")
    @click.option(
        "--originals-dir",
        default=None,
        help="originals のルート。未指定時は設定から解決。",
    )
    @click.option(
        "--refresh",
        is_flag=True,
        help="既存 Media のメタデータも再適用する。",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="変更を加えず件数のみ集計する。",
    )
    @click.option(
        "--verbose",
        is_flag=True,
        help="1件ごとの処理内容を表示する。",
    )
    def rebuild_originals(originals_dir, refresh, dry_run, verbose):
        """originals ディレクトリを直接走査して Media を再登録する（冪等）。"""
        from bounded_contexts.photonest.tasks.local_import import (
            rebuild_media_from_originals,
        )

        click.echo("=== Rebuild media from originals ===")
        if dry_run:
            click.echo("(dry-run: 変更は加えません)")

        stats = rebuild_media_from_originals(
            originals_dir=originals_dir,
            refresh_existing=refresh,
            dry_run=dry_run,
            progress=(lambda message: click.echo(f"  {message}")) if verbose else None,
        )

        click.echo(
            "\n".join(
                [
                    "",
                    f"scanned  : {stats['scanned']}",
                    f"created  : {stats['created']}",
                    f"refreshed: {stats['refreshed']}",
                    f"skipped  : {stats['skipped']}",
                    f"errors   : {stats['errors']}",
                ]
            )
        )
        if stats["errors"]:
            raise click.ClickException(f"{stats['errors']} 件のエラーが発生しました")

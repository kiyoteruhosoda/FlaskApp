from typing import Optional
import typer
from rich.console import Console
from rich.table import Table

from .version import __version__
from .config import PhotoNestConfig


console = Console()
app = typer.Typer(
    name="fpv",
    help="PhotoNest CLI (fpv): family photo sync utilities",
    no_args_is_help=True,
    add_completion=False,
)

# ---------------------------------------------------------------------------
# sub-app: config
config_app = typer.Typer(name="config", help="設定の表示と検証")
app.add_typer(config_app, name="config")


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        callback=lambda v: (_print_version() if v else None),
        is_eager=True,
        help="Show version and exit.",
    )
):
    return


def _print_version() -> None:
    console.print(f"[bold]fpv[/] version {__version__}")
    raise typer.Exit(code=0)


@config_app.command("show", help="環境変数から読み込んだ設定を表示（秘匿情報はマスク）")
def config_show() -> None:
    cfg = PhotoNestConfig.from_env()
    masked = cfg.masked()
    table = Table(title="PhotoNest Config (masked)")
    table.add_column("Key", style="bold")
    table.add_column("Value")

    for k, v in masked.items():
        table.add_row(k, str(v))
    console.print(table)


@config_app.command("check", help="設定を検証してエラー/警告を表示")
def config_check(
    strict_path: bool = typer.Option(
        False, "--strict-path", help="パス存在チェックを有効化"
    )
) -> None:
    base = PhotoNestConfig.from_env()
    cfg = PhotoNestConfig(
        **{**base.__dict__, "strict_path_check": strict_path or base.strict_path_check}
    )
    warns, errs = cfg.validate()
    if warns:
        console.print("[yellow]WARN[/] " + " | ".join(warns))
    if errs:
        console.print("[red]ERROR[/] " + " | ".join(errs))
        raise typer.Exit(code=1)
    console.print("[green]OK[/] 設定は有効です")


# ---------------------------------------------------------------------------
# existing commands


@app.command(help="Google Photos 差分取得（複数アカウント対応）")
def sync(
    all_accounts: bool = typer.Option(
        True,
        "--all-accounts/--single-account",
        help="すべてのactiveアカウントを処理（既定: True）",
    ),
    account_id: Optional[int] = typer.Option(
        None, "--account-id", help="単一アカウントIDを指定する場合に利用"
    ),
) -> None:
    cfg = PhotoNestConfig.from_env()
    _, errs = cfg.validate()
    if errs:
        console.print("[red]設定エラー[/]: ", "; ".join(errs))
        raise typer.Exit(1)
    console.print("[cyan]TODO[/]: sync（差分取得）の実装")


@app.command("import", help="既存ローカル取り込み（固定ディレクトリ）")
def import_(
    path: str = typer.Option(
        "/mnt/nas/import", "--path", help="取り込み対象ディレクトリ"
    ),
) -> None:
    cfg = PhotoNestConfig.from_env()
    _, errs = cfg.validate()
    if errs:
        console.print("[red]設定エラー[/]: ", "; ".join(errs))
        raise typer.Exit(1)
    console.print(f"[cyan]TODO[/]: import from {path}")


@app.command(help="未変換動画のスキャン→変換キュー投入＆処理")
def transcode(
    scan_pending: bool = typer.Option(
        True,
        "--scan-pending/--no-scan-pending",
        help="未変換スキャンを実施（既定: True）",
    ),
    max_workers: int = typer.Option(2, "--max-workers", min=1, help="並列数（既定: 2）"),
) -> None:
    cfg = PhotoNestConfig.from_env()
    _, errs = cfg.validate()
    if errs:
        console.print("[red]設定エラー[/]: ", "; ".join(errs))
        raise typer.Exit(1)
    console.print(
        f"[cyan]TODO[/]: transcode (scan={scan_pending}, workers={max_workers})"
    )


@app.command(help="サムネ未生成の検出→生成キュー投入")
def thumbs(
    scan_pending: bool = typer.Option(
        True,
        "--scan-pending/--no-scan-pending",
        help="未生成スキャン（既定: True）",
    ),
) -> None:
    cfg = PhotoNestConfig.from_env()
    _, errs = cfg.validate()
    if errs:
        console.print("[red]設定エラー[/]: ", "; ".join(errs))
        raise typer.Exit(1)
    console.print(f"[cyan]TODO[/]: thumbs (scan={scan_pending})")


@app.command(help="失敗ジョブの再試行")
def retry(
    older_than: str = typer.Option("1h", "--older-than", help="対象期間（例: 1h, 24h）"),
    max_retries: int = typer.Option(3, "--max-retries", min=1, help="最大再試行回数（既定: 3）"),
) -> None:
    cfg = PhotoNestConfig.from_env()
    _, errs = cfg.validate()
    if errs:
        console.print("[red]設定エラー[/]: ", "; ".join(errs))
        raise typer.Exit(1)
    console.print(
        f"[cyan]TODO[/]: retry (older_than={older_than}, max_retries={max_retries})"
    )


@app.command(help="一時領域のクリーンアップ")
def clean(
    tmp: bool = typer.Option(True, "--tmp/--no-tmp", help="一時領域を掃除（既定: True）"),
    days: int = typer.Option(7, "--days", min=1, help="保持日数（既定: 7）"),
) -> None:
    cfg = PhotoNestConfig.from_env()
    _, errs = cfg.validate()
    if errs:
        console.print("[red]設定エラー[/]: ", "; ".join(errs))
        raise typer.Exit(1)
    console.print(f"[cyan]TODO[/]: clean (tmp={tmp}, days={days})")


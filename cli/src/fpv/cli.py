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
config_app = typer.Typer(name="config", help="Show and validate configuration")
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


@config_app.command(
    "show",
    help="Display settings loaded from environment variables (sensitive values masked)",
)
def config_show() -> None:
    cfg = PhotoNestConfig.from_env()
    masked = cfg.masked()
    table = Table(title="PhotoNest Config (masked)")
    table.add_column("Key", style="bold")
    table.add_column("Value")

    for k, v in masked.items():
        table.add_row(k, str(v))
    console.print(table)


@config_app.command("check", help="Validate settings and show errors/warnings")
def config_check(
    strict_path: bool = typer.Option(
        False, "--strict-path", help="Enable path existence check"
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
    console.print("[green]OK[/] Configuration is valid")


# ---------------------------------------------------------------------------
# existing commands


@app.command(help="Sync Google Photos (multi-account)")
def sync(
    all_accounts: bool = typer.Option(
        True,
        "--all-accounts/--single-account",
        help="Process all active accounts (default: True)",
    ),
    account_id: Optional[int] = typer.Option(
        None, "--account-id", help="Process a single account by ID"
    ),
) -> None:
    cfg = PhotoNestConfig.from_env()
    _, errs = cfg.validate()
    if errs:
        console.print("[red]Configuration error[/]: " + "; ".join(errs))
        raise typer.Exit(1)
    console.print("[cyan]TODO[/]: implement sync")


@app.command("import", help="Import existing local files (fixed directory)")
def import_(
    path: str = typer.Option(
        "/mnt/nas/import", "--path", help="Target directory to import"
    ),
) -> None:
    cfg = PhotoNestConfig.from_env()
    _, errs = cfg.validate()
    if errs:
        console.print("[red]Configuration error[/]: " + "; ".join(errs))
        raise typer.Exit(1)
    console.print(f"[cyan]TODO[/]: import from {path}")


@app.command(help="Scan untranscoded videos and process the queue")
def transcode(
    scan_pending: bool = typer.Option(
        True,
        "--scan-pending/--no-scan-pending",
        help="Scan for pending items (default: True)",
    ),
    max_workers: int = typer.Option(2, "--max-workers", min=1, help="Concurrency (default: 2)"),
) -> None:
    cfg = PhotoNestConfig.from_env()
    _, errs = cfg.validate()
    if errs:
        console.print("[red]Configuration error[/]: " + "; ".join(errs))
        raise typer.Exit(1)
    console.print(
        f"[cyan]TODO[/]: transcode (scan={scan_pending}, workers={max_workers})"
    )


@app.command(help="Detect missing thumbnails and enqueue generation")
def thumbs(
    scan_pending: bool = typer.Option(
        True,
        "--scan-pending/--no-scan-pending",
        help="Scan for pending items (default: True)",
    ),
) -> None:
    cfg = PhotoNestConfig.from_env()
    _, errs = cfg.validate()
    if errs:
        console.print("[red]Configuration error[/]: " + "; ".join(errs))
        raise typer.Exit(1)
    console.print(f"[cyan]TODO[/]: thumbs (scan={scan_pending})")


@app.command(help="Retry failed jobs")
def retry(
    older_than: str = typer.Option("1h", "--older-than", help="Window to target (e.g. 1h, 24h)"),
    max_retries: int = typer.Option(3, "--max-retries", min=1, help="Max retry count (default: 3)"),
) -> None:
    cfg = PhotoNestConfig.from_env()
    _, errs = cfg.validate()
    if errs:
        console.print("[red]Configuration error[/]: " + "; ".join(errs))
        raise typer.Exit(1)
    console.print(
        f"[cyan]TODO[/]: retry (older_than={older_than}, max_retries={max_retries})"
    )


@app.command(help="Cleanup temporary area")
def clean(
    tmp: bool = typer.Option(True, "--tmp/--no-tmp", help="Clean temporary files (default: True)"),
    days: int = typer.Option(7, "--days", min=1, help="Retention days (default: 7)"),
) -> None:
    cfg = PhotoNestConfig.from_env()
    _, errs = cfg.validate()
    if errs:
        console.print("[red]Configuration error[/]: " + "; ".join(errs))
        raise typer.Exit(1)
    console.print(f"[cyan]TODO[/]: clean (tmp={tmp}, days={days})")


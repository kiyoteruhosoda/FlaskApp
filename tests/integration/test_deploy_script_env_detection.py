"""deploy.sh の環境判定（配置ディレクトリ → stg / prod）の回帰テスト。

deploy.sh は自身の配置場所から環境を自動判定する。受け付ける配置は2通り:

- ``<env>/scripts/deploy.sh`` … 正規配置（``dist/scripts/deploy.sh`` を pick）
- ``<env>/deploy.sh``         … トップレベル配置（旧来の NAS 側ランチャーが実行するパス）

2026-07-20 の prod デプロイ失敗調査で、ランチャー（git 管理外）が
``<env>/deploy.sh`` を実行し続けており、pick が更新する
``<env>/scripts/deploy.sh`` と食い違って古い版が動く事故が判明した。
トップレベル配置を弾くと、ランチャー側を直すまで一切デプロイできなくなるため、
両配置を正規に受け付けることを検証する。

環境判定は docker 等の外部コマンドに触れる前に走るため、モード引数なしで実行し
「配置エラーで落ちるか、モード必須エラーまで到達するか」で判定する（Docker 不要）。
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SH = ROOT / "scripts" / "deploy.sh"


def _run_from(placed_at: Path) -> subprocess.CompletedProcess[str]:
    placed_at.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(DEPLOY_SH, placed_at)
    placed_at.chmod(0o755)
    return subprocess.run(
        ["bash", str(placed_at)],
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.mark.parametrize(
    "relative_path",
    [
        "photonest/stg/scripts/deploy.sh",
        "photonest/prod/scripts/deploy.sh",
        "photonest/stg/deploy.sh",
        "photonest/prod/deploy.sh",
    ],
)
def test_accepted_placements_reach_mode_check(tmp_path: Path, relative_path: str) -> None:
    """正規配置・トップレベル配置とも環境判定を通過してモード必須エラーへ到達する。"""
    result = _run_from(tmp_path / relative_path)
    assert result.returncode == 1
    assert "Mode required" in result.stderr, (
        f"{relative_path} からの実行が環境判定を通過していません: {result.stderr}"
    )


def test_unknown_placement_is_rejected(tmp_path: Path) -> None:
    """stg / prod いずれにも該当しない配置は明示エラーで拒否する。"""
    result = _run_from(tmp_path / "photonest/deploy.sh")
    assert result.returncode == 1
    assert "stg / prod" in result.stderr, (
        f"不正配置がエラーになっていません: {result.stderr}"
    )

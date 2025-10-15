"""CLI サブパッケージ初期化モジュール."""

from __future__ import annotations

import sys
from pathlib import Path

# プロジェクトルートを Python パスへ追加して、
# `features` などのトップレベルパッケージを CLI 実行時にも解決できるようにする。
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_project_root_str = str(_PROJECT_ROOT)
if _project_root_str not in sys.path:
    sys.path.insert(0, _project_root_str)

__all__ = ["_PROJECT_ROOT"]

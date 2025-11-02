"""Google フォト取り込み用クライアント（スタブ実装）。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List


@dataclass(slots=True)
class GoogleMediaClient:
    """Google API 呼び出しを抽象化するクライアント."""

    def list_media(self, account_id: str, *, page_size: int = 100) -> List[dict]:
        """指定アカウントからメディアメタデータを取得するスタブ実装."""

        # 実装は今後の拡張で提供される。現状は空リストを返す。
        return []


__all__ = ["GoogleMediaClient"]

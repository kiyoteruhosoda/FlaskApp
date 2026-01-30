"""Google フォト取り込み用クライアント（スタブ実装）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional


@dataclass(slots=True)
class GoogleMediaItem:
    """Google フォト API から取得したメディアメタデータの表現."""

    id: str
    filename: str
    mime_type: str
    size_bytes: int
    width: Optional[int] = None
    height: Optional[int] = None
    duration_ms: Optional[int] = None
    shot_at: Optional[datetime] = None
    download_url: Optional[str] = None
    checksum: Optional[str] = None
    is_video: Optional[bool] = None
    orientation: Optional[int] = None
    perceptual_hash: Optional[str] = None
    exif: Dict[str, Any] = field(default_factory=dict)
    video_metadata: Dict[str, Any] = field(default_factory=dict)

    def resolved_shot_at(self) -> datetime:
        """API から shot_at が得られない場合のフォールバックを提供する."""

        return self.shot_at or datetime.now(timezone.utc)


@dataclass(slots=True)
class GoogleMediaClient:
    """Google API 呼び出しを抽象化するクライアント."""

    def list_media(self, account_id: str, *, page_size: int = 100) -> List[GoogleMediaItem]:
        """指定アカウントからメディアメタデータを取得するスタブ実装."""

        # 実装は今後の拡張で提供される。現状は空リストを返す。
        return []


__all__ = ["GoogleMediaClient", "GoogleMediaItem"]

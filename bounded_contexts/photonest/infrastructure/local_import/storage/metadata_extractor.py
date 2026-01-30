"""メタデータ抽出の実装."""
from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, Optional

from bounded_contexts.photonest.domain.local_import.media_metadata import (
    calculate_file_hash,
    extract_exif_data,
    extract_video_metadata,
    get_image_dimensions,
)


class MetadataExtractor:
    """ファイルからメタデータを抽出する実装.
    
    責務：
    - ファイルハッシュの計算
    - EXIF/動画メタデータの抽出
    - 撮影日時の正規化
    """
    
    def extract(self, file_path: str) -> Dict[str, Any]:
        """ファイルからメタデータを抽出.
        
        Args:
            file_path: 対象ファイルパス
            
        Returns:
            メタデータ辞書
            - hash: SHA-256ハッシュ
            - size: ファイルサイズ（バイト）
            - phash: 知覚的ハッシュ（画像/動画のみ）
            - shot_at: 撮影日時（UTC）
            - width: 幅
            - height: 高さ
            - duration_ms: 長さ（ミリ秒、動画のみ）
            - is_video: 動画フラグ
            - mime_type: MIMEタイプ
            - extension: 拡張子
        """
        import os
        from pathlib import Path
        
        # 基本情報
        file_size = os.path.getsize(file_path)
        file_hash = calculate_file_hash(file_path)
        extension = Path(file_path).suffix
        
        # 動画判定（拡張子ベース）
        video_extensions = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
        is_video = extension.lower() in video_extensions
        
        metadata: Dict[str, Any] = {
            "hash": file_hash,
            "size": file_size,
            "extension": extension,
            "is_video": is_video,
        }
        
        if is_video:
            # 動画メタデータ抽出
            video_meta = extract_video_metadata(file_path)
            metadata.update({
                "width": video_meta.get("width"),
                "height": video_meta.get("height"),
                "duration_ms": video_meta.get("duration_ms"),
                "mime_type": video_meta.get("mime_type", "video/mp4"),
                "shot_at": self._normalize_datetime(video_meta.get("creation_time")),
            })
        else:
            # 画像メタデータ抽出
            try:
                dimensions = get_image_dimensions(file_path)
                metadata.update({
                    "width": dimensions[0] if dimensions else None,
                    "height": dimensions[1] if dimensions else None,
                })
            except Exception:
                pass
            
            # EXIF抽出
            try:
                exif = extract_exif_data(file_path)
                metadata.update({
                    "shot_at": self._normalize_datetime(exif.get("DateTimeOriginal")),
                    "mime_type": "image/jpeg",  # 簡易実装
                })
            except Exception:
                pass
        
        return metadata
    
    @staticmethod
    def _normalize_datetime(value: Any) -> Optional[datetime]:
        """日時を正規化（UTC）."""
        if isinstance(value, datetime):
            # タイムゾーン情報がない場合はUTCとみなす
            if value.tzinfo is None:
                from datetime import timezone
                return value.replace(tzinfo=timezone.utc)
            return value
        
        if isinstance(value, str):
            # 文字列からのパース（簡易実装）
            try:
                from datetime import timezone
                from dateutil import parser
                parsed = parser.parse(value)
                if parsed.tzinfo is None:
                    return parsed.replace(tzinfo=timezone.utc)
                return parsed
            except Exception:
                return None
        
        return None

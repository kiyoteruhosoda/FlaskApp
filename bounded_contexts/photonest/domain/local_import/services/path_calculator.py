"""パス計算のドメインサービス."""
from __future__ import annotations
from datetime import datetime
from typing import Optional

from ..value_objects import RelativePath


class PathCalculator:
    """ファイルパス計算のドメインサービス.
    
    ビジネスルール：
    - 撮影日時ベースでディレクトリ階層を決定（YYYY/MM/DD/）
    - ファイル名: YYYYMMDD_HHMMSS_src_hash8.ext
    """
    
    def calculate_storage_path(
        self,
        shot_at: Optional[datetime],
        source_type: str,
        file_hash: str,
        extension: str,
    ) -> RelativePath:
        """保存先の相対パスを計算.
        
        Args:
            shot_at: 撮影日時（UTC）
            source_type: ソース種別（gphotos/local/cam）
            file_hash: ファイルハッシュ（SHA-256）
            extension: 拡張子（ドット含む、例: .jpg）
            
        Returns:
            相対パス（例: 2025/01/15/20250115_123045_local_a1b2c3d4.jpg）
        """
        if not shot_at:
            # 撮影日時不明の場合はデフォルトディレクトリ
            shot_at = datetime(1970, 1, 1)
        
        # ディレクトリ構造: YYYY/MM/DD
        year = f"{shot_at.year:04d}"
        month = f"{shot_at.month:02d}"
        day = f"{shot_at.day:02d}"
        
        # ファイル名: YYYYMMDD_HHMMSS_src_hash8.ext
        date_str = f"{shot_at.year:04d}{shot_at.month:02d}{shot_at.day:02d}"
        time_str = f"{shot_at.hour:02d}{shot_at.minute:02d}{shot_at.second:02d}"
        hash_prefix = file_hash[:8] if file_hash else "unknown"
        
        # 拡張子の正規化
        ext = extension.lower() if extension.startswith(".") else f".{extension.lower()}"
        
        filename = f"{date_str}_{time_str}_{source_type}_{hash_prefix}{ext}"
        rel_path = f"{year}/{month}/{day}/{filename}"
        
        return RelativePath(rel_path)
    
    def rebase_path(
        self,
        current_path: RelativePath,
        new_base_path: RelativePath,
    ) -> RelativePath:
        """既存ファイルのパスを新しいベースパスに合わせて再配置.
        
        Args:
            current_path: 現在の相対パス
            new_base_path: 新しいベースパス
            
        Returns:
            再配置後の相対パス
        """
        # 新しいベースのディレクトリ部分を取得
        new_dir = new_base_path.parent()
        current_filename = current_path.value.split("/")[-1]
        
        # 新しいディレクトリ + 現在のファイル名
        rebased = f"{new_dir.value}/{current_filename}"
        return RelativePath(rebased)
    
    def calculate_playback_path(
        self,
        original_path: RelativePath,
        suffix: str = "_play",
    ) -> RelativePath:
        """再生用ファイルのパスを計算.
        
        Args:
            original_path: 原本の相対パス
            suffix: ファイル名に追加するサフィックス
            
        Returns:
            再生用ファイルの相対パス
        """
        stem = original_path.stem()
        parent = original_path.parent()
        
        playback_filename = f"{stem}{suffix}.mp4"
        playback_path = f"{parent.value}/{playback_filename}"
        
        return RelativePath(playback_path)

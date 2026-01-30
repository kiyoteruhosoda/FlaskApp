"""重複メディアチェックのドメインサービス."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol

from ..value_objects import FileHash


class MediaEntity(Protocol):
    """メディアエンティティのプロトコル（インターフェース）."""
    
    id: int
    hash_sha256: str
    bytes: int
    phash: Optional[str]
    is_video: bool
    shot_at: Optional[datetime]
    width: Optional[int]
    height: Optional[int]
    duration_ms: Optional[int]
    is_deleted: bool


@dataclass(frozen=True)
class MediaSignature:
    """メディアを一意に識別するための署名."""
    
    file_hash: FileHash
    shot_at: Optional[datetime]
    width: Optional[int]
    height: Optional[int]
    duration_ms: Optional[int]
    is_video: bool
    
    def matches_exact(self, other: MediaSignature) -> bool:
        """完全一致判定（全属性が一致）."""
        return (
            self.file_hash.matches_cryptographic(other.file_hash)
            and self.shot_at == other.shot_at
            and self.width == other.width
            and self.height == other.height
            and self.duration_ms == other.duration_ms
            and self.is_video == other.is_video
        )
    
    def matches_perceptual(self, other: MediaSignature) -> bool:
        """知覚的一致判定（pHash + メタデータ）."""
        if not self.file_hash.perceptual_hash or not other.file_hash.perceptual_hash:
            return False
        
        return (
            self.file_hash.matches_perceptual(other.file_hash)
            and self.is_video == other.is_video
            and self.duration_ms == other.duration_ms
        )
    
    def matches_loose(self, other: MediaSignature) -> bool:
        """緩い一致判定（ハッシュのみ）."""
        return self.file_hash.matches_cryptographic(other.file_hash)


class MediaDuplicateChecker:
    """メディア重複チェックのドメインサービス.
    
    ビジネスルール：
    1. 優先度1: pHash + 解像度 + 撮影日時 + 動画長
    2. 優先度2: pHash + 動画長（撮影日時・解像度不一致）
    3. 優先度3: SHA-256 + サイズ（pHashなし）
    """
    
    def find_duplicate(
        self,
        signature: MediaSignature,
        candidates: list[MediaEntity],
    ) -> Optional[MediaEntity]:
        """重複メディアを検索.
        
        Args:
            signature: 新規ファイルの署名
            candidates: 検索対象のメディアリスト
            
        Returns:
            重複が見つかった場合はそのメディア、なければNone
        """
        # フィルタリング: 削除済み・動画フラグ不一致を除外
        valid_candidates = [
            c for c in candidates
            if not c.is_deleted and c.is_video == signature.is_video
        ]
        
        # 優先度1: 完全一致（pHash + メタデータ）
        if signature.file_hash.perceptual_hash:
            for candidate in valid_candidates:
                candidate_sig = self._to_signature(candidate)
                if signature.matches_exact(candidate_sig):
                    return candidate
        
        # 優先度2: 知覚的一致（pHashのみ）
        if signature.file_hash.perceptual_hash:
            for candidate in valid_candidates:
                candidate_sig = self._to_signature(candidate)
                if signature.matches_perceptual(candidate_sig):
                    return candidate
        
        # 優先度3: 暗号学的一致（SHA-256 + サイズ）
        for candidate in valid_candidates:
            candidate_sig = self._to_signature(candidate)
            if signature.matches_loose(candidate_sig):
                return candidate
        
        return None
    
    @staticmethod
    def _to_signature(media: MediaEntity) -> MediaSignature:
        """MediaEntityからMediaSignatureを生成."""
        file_hash = FileHash(
            sha256=media.hash_sha256,
            size_bytes=media.bytes,
            perceptual_hash=media.phash,
        )
        return MediaSignature(
            file_hash=file_hash,
            shot_at=media.shot_at,
            width=media.width,
            height=media.height,
            duration_ms=media.duration_ms,
            is_video=media.is_video,
        )

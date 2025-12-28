"""メディアリポジトリの実装."""
from __future__ import annotations
from datetime import datetime
from typing import List, Optional

from core.models.photo_models import Media
from features.photonest.domain.local_import.services import MediaSignature


class MediaRepositoryImpl:
    """MediaエンティティのRepository実装.
    
    責務：
    - ORMモデル（Media）への永続化
    - ドメインオブジェクトとORMモデル間の変換
    - 重複検索クエリの実行
    """
    
    def __init__(self, db_session) -> None:
        self._db = db_session
    
    def find_by_signature(self, signature: MediaSignature) -> Optional[Media]:
        """署名によるメディア検索.
        
        検索戦略：
        1. pHash + メタデータによる完全一致
        2. pHashのみによる知覚的一致
        3. SHA-256 + サイズによる暗号学的一致
        """
        # 基本フィルタ: 削除済み除外、動画フラグ一致
        base_query = Media.query.filter(
            Media.is_deleted.is_(False),
            Media.is_video.is_(signature.is_video),
        )
        
        # 動画の場合は長さも一致
        if signature.is_video and signature.duration_ms is not None:
            base_query = base_query.filter(Media.duration_ms == signature.duration_ms)
        
        # 優先度1: pHash + メタデータ完全一致
        if signature.file_hash.perceptual_hash and signature.shot_at:
            candidate = base_query.filter(
                Media.phash == signature.file_hash.perceptual_hash,
                Media.shot_at == signature.shot_at,
                Media.width == signature.width,
                Media.height == signature.height,
            ).first()
            if candidate:
                return candidate
        
        # 優先度2: pHashのみ一致
        if signature.file_hash.perceptual_hash:
            candidates = base_query.filter(
                Media.phash == signature.file_hash.perceptual_hash,
            ).all()
            if candidates:
                # 撮影日時・解像度も一致するものを優先
                for candidate in candidates:
                    if (
                        candidate.shot_at == signature.shot_at
                        and candidate.width == signature.width
                        and candidate.height == signature.height
                    ):
                        return candidate
                # 一致しなければ最初の候補を返す
                return candidates[0]
        
        # 優先度3: SHA-256 + サイズ一致
        return Media.query.filter_by(
            hash_sha256=signature.file_hash.sha256,
            bytes=signature.file_hash.size_bytes,
            is_deleted=False,
        ).first()
    
    def find_candidates_by_metadata(
        self,
        *,
        is_video: bool,
        shot_at: Optional[datetime],
        width: Optional[int],
        height: Optional[int],
        duration_ms: Optional[int],
    ) -> List[Media]:
        """メタデータによる候補検索（重複チェック用）."""
        query = Media.query.filter(
            Media.is_deleted.is_(False),
            Media.is_video.is_(is_video),
        )
        
        if shot_at:
            query = query.filter(Media.shot_at == shot_at)
        
        if width and height:
            query = query.filter(
                Media.width == width,
                Media.height == height,
            )
        
        if is_video and duration_ms is not None:
            query = query.filter(Media.duration_ms == duration_ms)
        
        return query.all()
    
    def save(self, media: Media) -> None:
        """メディアを保存."""
        self._db.session.add(media)
        self._db.session.flush()
    
    def get_by_id(self, media_id: int) -> Optional[Media]:
        """IDによるメディア取得."""
        return Media.query.get(media_id)

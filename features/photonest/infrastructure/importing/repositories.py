"""インポート関連のリポジトリアダプタ."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from core.models.photo_models import Media as MediaModel

from ...domain.importing.import_session import ImportSession
from ...domain.importing.media import Media
from ...domain.importing.media_hash import MediaHash


@dataclass(slots=True)
class SqlAlchemyMediaRepository:
    """SQLAlchemy を利用した :class:`MediaRepository` 実装."""

    session: Session

    def exists_by_hash(self, media_hash: MediaHash) -> bool:
        query = self.session.query(MediaModel.id).filter(
            MediaModel.hash_sha256 == media_hash.value
        )
        return self.session.query(query.exists()).scalar() is True

    def save_media(self, media: Media, import_session: ImportSession) -> MediaModel:
        model = MediaModel(
            google_media_id=media.extras.get("google_media_id"),
            account_id=media.extras.get("account_id"),
            local_rel_path=media.relative_path,
            filename=media.filename,
            hash_sha256=media.hash.value,
            phash=media.perceptual_hash,
            bytes=media.size_bytes,
            mime_type=media.analysis.mime_type,
            width=media.analysis.width,
            height=media.analysis.height,
            duration_ms=media.analysis.duration_ms,
            shot_at=media.analysis.shot_at,
            imported_at=import_session.started_at,
            orientation=media.analysis.orientation,
            is_video=media.analysis.is_video,
        )
        self.session.add(model)
        return model


__all__ = ["SqlAlchemyMediaRepository"]

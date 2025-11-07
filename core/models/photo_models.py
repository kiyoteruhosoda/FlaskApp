"""Photo related ORM models using SQLAlchemy 2.x typing syntax."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import db

if TYPE_CHECKING:  # pragma: no cover
    from core.models.google_account import GoogleAccount
    from core.models.picker_session import PickerSession

BigInt = db.BigInteger().with_variant(db.Integer, "sqlite")

# --- 中間テーブル ---
album_item = db.Table(
    "album_item",
    db.Column("album_id", BigInt, db.ForeignKey("album.id"), primary_key=True),
    db.Column("media_id", BigInt, db.ForeignKey("media.id"), primary_key=True),
    db.Column("sort_index", BigInt),
)

media_tag = db.Table(
    "media_tag",
    db.Column("media_id", BigInt, db.ForeignKey("media.id"), primary_key=True),
    db.Column("tag_id", BigInt, db.ForeignKey("tag.id"), primary_key=True),
)


class Media(db.Model):
    __tablename__ = "media"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)

    # ソース情報
    source_type: Mapped[str] = mapped_column(
        db.Enum("local", "google_photos", "wiki-media", name="media_source_type"),
        nullable=False,
        default="local",
    )
    google_media_id: Mapped[str | None] = mapped_column(db.String(255), nullable=True)
    account_id: Mapped[int | None] = mapped_column(
        BigInt,
        db.ForeignKey("google_account.id"),
        nullable=True,
    )
    account: Mapped["GoogleAccount | None"] = relationship(
        "GoogleAccount",
        back_populates="media_items",
    )

    # ファイル情報
    local_rel_path: Mapped[str | None] = mapped_column(db.String(255), nullable=True)
    thumbnail_rel_path: Mapped[str | None] = mapped_column(db.String(255), nullable=True)
    filename: Mapped[str | None] = mapped_column(db.String(255), nullable=True)
    hash_sha256: Mapped[str | None] = mapped_column(db.CHAR(64), nullable=True)
    phash: Mapped[str | None] = mapped_column(db.String(64), nullable=True)
    bytes: Mapped[int | None] = mapped_column(BigInt, nullable=True)

    # メディア情報
    mime_type: Mapped[str | None] = mapped_column(db.String(255), nullable=True)
    width: Mapped[int | None] = mapped_column(db.Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(db.Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(db.Integer, nullable=True)
    orientation: Mapped[int | None] = mapped_column(db.Integer, nullable=True)
    is_video: Mapped[bool] = mapped_column(db.Boolean, default=False, nullable=False)

    # 撮影情報
    shot_at: Mapped[datetime | None] = mapped_column(db.DateTime, nullable=True)
    camera_make: Mapped[str | None] = mapped_column(db.String(255), nullable=True)
    camera_model: Mapped[str | None] = mapped_column(db.String(255), nullable=True)

    # 管理情報
    imported_at: Mapped[datetime] = mapped_column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    is_deleted: Mapped[bool] = mapped_column(db.Boolean, default=False, nullable=False)
    has_playback: Mapped[bool] = mapped_column(db.Boolean, default=False, nullable=False)
    live_group_id: Mapped[int | None] = mapped_column(BigInt, nullable=True)

    # タイムスタンプ
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # リレーション
    sidecars: Mapped[list["MediaSidecar"]] = relationship(
        "MediaSidecar",
        back_populates="media",
        cascade="all, delete-orphan",
    )
    exif: Mapped["Exif | None"] = relationship(
        "Exif",
        back_populates="media",
        uselist=False,
    )
    albums: Mapped[list["Album"]] = relationship(
        "Album",
        secondary=album_item,
        back_populates="media",
    )
    tags: Mapped[list["Tag"]] = relationship(
        "Tag",
        secondary=media_tag,
        back_populates="media",
    )
    playbacks: Mapped[list["MediaPlayback"]] = relationship(
        "MediaPlayback",
        back_populates="media",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Media {self.id}: {self.source_type} - {self.filename or self.google_media_id}>"

    @property
    def display_name(self) -> str:
        """表示用の名前を返す（撮影日時ベース）。"""

        if self.shot_at:
            return self.shot_at.strftime("%Y-%m-%d %H:%M")
        if self.created_at:
            return f"Import {self.created_at.strftime('%Y-%m-%d %H:%M')}"
        return f"Media {self.id}"

    @property
    def is_local(self) -> bool:
        return self.source_type == "local"

    @property
    def is_google_photos(self) -> bool:
        return self.source_type == "google_photos"

    @property
    def resolved_thumbnail_rel_path(self) -> str | None:
        """サムネイル用の相対パスを返す。"""

        return self.thumbnail_rel_path or self.local_rel_path


class MediaSidecar(db.Model):
    __tablename__ = "media_sidecar"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    media_id: Mapped[int] = mapped_column(
        BigInt,
        db.ForeignKey("media.id"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(
        db.Enum("video", "audio", "subtitle", name="media_sidecar_type"),
        nullable=False,
    )
    rel_path: Mapped[str | None] = mapped_column(db.String(255), nullable=True)
    bytes: Mapped[int | None] = mapped_column(BigInt, nullable=True)

    media: Mapped[Media] = relationship(
        "Media",
        back_populates="sidecars",
    )


class Exif(db.Model):
    __tablename__ = "exif"

    media_id: Mapped[int] = mapped_column(BigInt, db.ForeignKey("media.id"), primary_key=True)
    camera_make: Mapped[str | None] = mapped_column(db.String(255), nullable=True)
    camera_model: Mapped[str | None] = mapped_column(db.String(255), nullable=True)
    lens: Mapped[str | None] = mapped_column(db.String(255), nullable=True)
    iso: Mapped[int | None] = mapped_column(db.Integer, nullable=True)
    shutter: Mapped[str | None] = mapped_column(db.String(32), nullable=True)
    f_number: Mapped[float | None] = mapped_column(db.Numeric(5, 2), nullable=True)
    focal_len: Mapped[float | None] = mapped_column(db.Numeric(5, 2), nullable=True)
    gps_lat: Mapped[float | None] = mapped_column(db.Numeric(10, 7), nullable=True)
    gps_lng: Mapped[float | None] = mapped_column(db.Numeric(10, 7), nullable=True)
    raw_json: Mapped[str | None] = mapped_column(db.Text, nullable=True)

    media: Mapped[Media] = relationship(
        "Media",
        back_populates="exif",
    )

    def __init__(
        self,
        media_id: int,
        camera_make: Optional[str] = None,
        camera_model: Optional[str] = None,
        lens: Optional[str] = None,
        iso: Optional[int] = None,
        shutter: Optional[str] = None,
        f_number: Optional[float] = None,
        focal_len: Optional[float] = None,
        gps_lat: Optional[float] = None,
        gps_lng: Optional[float] = None,
        raw_json: Optional[str] = None,
    ) -> None:
        """Exif モデルのコンストラクタ（型チェック対応）"""
        self.media_id = media_id
        self.camera_make = camera_make
        self.camera_model = camera_model
        self.lens = lens
        self.iso = iso
        self.shutter = shutter
        self.f_number = f_number
        self.focal_len = focal_len
        self.gps_lat = gps_lat
        self.gps_lng = gps_lng
        self.raw_json = raw_json


class Album(db.Model):
    __tablename__ = "album"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(db.String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(db.Text, nullable=True)
    cover_media_id: Mapped[int | None] = mapped_column(BigInt, db.ForeignKey("media.id"), nullable=True)
    visibility: Mapped[str] = mapped_column(
        db.Enum("public", "private", "unlisted", name="album_visibility"),
        nullable=False,
    )
    display_order: Mapped[int | None] = mapped_column(db.Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    media: Mapped[list[Media]] = relationship(
        "Media",
        secondary=album_item,
        back_populates="albums",
    )
    cover_media: Mapped[Media | None] = relationship("Media", foreign_keys=[cover_media_id])


class Tag(db.Model):
    __tablename__ = "tag"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(db.String(255), nullable=False)
    attr: Mapped[str] = mapped_column(
        db.Enum(
            "thing",
            "person",
            "place",
            "event",
            "scene",
            "activity",
            "source",
            "others",
            name="tag_attr",
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    created_by: Mapped[int | None] = mapped_column(BigInt, db.ForeignKey("user.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    media: Mapped[list[Media]] = relationship(
        "Media",
        secondary=media_tag,
        back_populates="tags",
    )


class MediaPlayback(db.Model):
    __tablename__ = "media_playback"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    media_id: Mapped[int] = mapped_column(BigInt, db.ForeignKey("media.id"), nullable=False)
    preset: Mapped[str] = mapped_column(
        db.Enum("original", "preview", "mobile", "std1080p", name="media_playback_preset"),
        nullable=False,
    )
    rel_path: Mapped[str | None] = mapped_column(db.String(255), nullable=True)
    width: Mapped[int | None] = mapped_column(db.Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(db.Integer, nullable=True)
    v_codec: Mapped[str | None] = mapped_column(db.String(32), nullable=True)
    a_codec: Mapped[str | None] = mapped_column(db.String(32), nullable=True)
    v_bitrate_kbps: Mapped[int | None] = mapped_column(db.Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(db.Integer, nullable=True)
    poster_rel_path: Mapped[str | None] = mapped_column(db.String(255), nullable=True)
    hash_sha256: Mapped[str | None] = mapped_column(db.CHAR(64), nullable=True)
    status: Mapped[str] = mapped_column(
        db.Enum("pending", "processing", "done", "error", name="media_playback_status"),
        nullable=False,
    )
    error_msg: Mapped[str | None] = mapped_column(db.Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    media: Mapped[Media] = relationship(
        "Media",
        back_populates="playbacks",
    )

    def __init__(
        self,
        media_id: int,
        preset: str,
        rel_path: str | None = None,
        poster_rel_path: str | None = None,
        status: str = "pending",
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        self.media_id = media_id
        self.preset = preset
        self.rel_path = rel_path
        self.poster_rel_path = poster_rel_path
        self.status = status
        self.created_at = created_at or datetime.now(timezone.utc)
        self.updated_at = updated_at or datetime.now(timezone.utc)

    def update_paths(self, rel_path: str | None, poster_rel_path: str | None) -> None:
        """再生用およびポスター用のパスを更新する."""

        self.rel_path = rel_path
        self.poster_rel_path = poster_rel_path
        self.updated_at = datetime.now(timezone.utc)


class MediaItem(db.Model):
    __tablename__ = "media_item"

    id: Mapped[str] = mapped_column(db.String(255), primary_key=True)
    type: Mapped[str] = mapped_column(
        db.Enum("TYPE_UNSPECIFIED", "PHOTO", "VIDEO", name="media_item_type"),
        nullable=False,
    )
    mime_type: Mapped[str | None] = mapped_column(db.String(255), nullable=True)
    filename: Mapped[str | None] = mapped_column(db.String(255), nullable=True)
    width: Mapped[int | None] = mapped_column(db.Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(db.Integer, nullable=True)
    camera_make: Mapped[str | None] = mapped_column(db.String(255), nullable=True)
    camera_model: Mapped[str | None] = mapped_column(db.String(255), nullable=True)
    photo_metadata_id: Mapped[int | None] = mapped_column(
        BigInt,
        db.ForeignKey("photo_metadata.id"),
        nullable=True,
    )
    video_metadata_id: Mapped[int | None] = mapped_column(
        BigInt,
        db.ForeignKey("video_metadata.id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    photo_metadata: Mapped["PhotoMetadata | None"] = relationship(
        "PhotoMetadata",
        back_populates="media_item",
        cascade="all, delete-orphan",
        single_parent=True,
        uselist=False,
    )
    video_metadata: Mapped["VideoMetadata | None"] = relationship(
        "VideoMetadata",
        back_populates="media_item",
        uselist=False,
    )
    picker_selections: Mapped[list["PickerSelection"]] = relationship(
        "PickerSelection",
        back_populates="media_item",
        cascade="all, delete-orphan",
    )


class PickerSelection(db.Model):
    __tablename__ = "picker_selection"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        BigInt,
        db.ForeignKey("picker_session.id"),
        nullable=False,
    )
    google_media_id: Mapped[str | None] = mapped_column(
        db.String(255),
        db.ForeignKey("media_item.id"),
        nullable=True,
    )
    local_file_path: Mapped[str | None] = mapped_column(db.Text, nullable=True)
    local_filename: Mapped[str | None] = mapped_column(db.String(500), nullable=True)
    status: Mapped[str] = mapped_column(
        db.Enum(
            "pending",
            "enqueued",
            "running",
            "imported",
            "dup",
            "failed",
            "expired",
            "skipped",
            name="picker_selection_status",
        ),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    create_time: Mapped[datetime | None] = mapped_column(db.DateTime, nullable=True)
    enqueued_at: Mapped[datetime | None] = mapped_column(db.DateTime, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(db.DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(db.DateTime, nullable=True)
    attempts: Mapped[int] = mapped_column(db.Integer, nullable=False, default=0, server_default="0")
    error_msg: Mapped[str | None] = mapped_column(db.Text, nullable=True)
    base_url: Mapped[str | None] = mapped_column(db.Text, nullable=True)
    base_url_fetched_at: Mapped[datetime | None] = mapped_column(db.DateTime, nullable=True)
    base_url_valid_until: Mapped[datetime | None] = mapped_column(db.DateTime, nullable=True)
    locked_by: Mapped[str | None] = mapped_column(db.String(255), nullable=True)
    lock_heartbeat_at: Mapped[datetime | None] = mapped_column(db.DateTime, nullable=True)
    last_transition_at: Mapped[datetime | None] = mapped_column(db.DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        db.UniqueConstraint(
            "session_id",
            "google_media_id",
            name="uq_picker_selection_session_media",
        ),
        db.Index("idx_picker_selection_session_status", "session_id", "status"),
        db.Index("idx_picker_selection_status_lock", "status", "lock_heartbeat_at"),
    )

    media_item: Mapped["MediaItem | None"] = relationship(
        "MediaItem",
        back_populates="picker_selections",
    )
    session: Mapped["PickerSession"] = relationship(
        "PickerSession",
        back_populates="picker_selections",
    )


class PhotoMetadata(db.Model):
    __tablename__ = "photo_metadata"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    focal_length: Mapped[float | None] = mapped_column(db.Float, nullable=True)
    aperture_f_number: Mapped[float | None] = mapped_column(db.Float, nullable=True)
    iso_equivalent: Mapped[int | None] = mapped_column(db.Integer, nullable=True)
    exposure_time: Mapped[str | None] = mapped_column(db.String(32), nullable=True)

    media_item: Mapped[MediaItem] = relationship(
        "MediaItem",
        back_populates="photo_metadata",
    )


class VideoMetadata(db.Model):
    __tablename__ = "video_metadata"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    fps: Mapped[float | None] = mapped_column(db.Float, nullable=True)
    processing_status: Mapped[str | None] = mapped_column(
        db.Enum("UNSPECIFIED", "PROCESSING", "READY", "FAILED", name="video_processing_status"),
        nullable=True,
    )

    media_item: Mapped[MediaItem] = relationship(
        "MediaItem",
        back_populates="video_metadata",
    )

# SQLAlchemy models for the ER diagram provided
# Each class represents a table in the database


from datetime import datetime, timezone
from core.db import db

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
    id = db.Column(BigInt, primary_key=True, autoincrement=True)
    google_media_id = db.Column(db.String(255), nullable=False)
    account_id = db.Column(BigInt, db.ForeignKey('google_account.id'), nullable=False)
    local_rel_path = db.Column(db.String(255))
    hash_sha256 = db.Column(db.CHAR(64))
    bytes = db.Column(BigInt)
    mime_type = db.Column(db.String(255))
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)
    duration_ms = db.Column(db.Integer)
    shot_at = db.Column(db.DateTime)
    imported_at = db.Column(db.DateTime)
    orientation = db.Column(db.Integer)
    is_video = db.Column(db.Boolean)
    live_group_id = db.Column(BigInt)
    is_deleted = db.Column(db.Boolean)
    has_playback = db.Column(db.Boolean)
    sidecars = db.relationship('MediaSidecar', backref='media')
    exif = db.relationship('Exif', uselist=False, backref='media')
    albums = db.relationship('Album', secondary=album_item, backref='media')
    tags = db.relationship('Tag', secondary=media_tag, backref='media')
    playbacks = db.relationship('MediaPlayback', backref='media')
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), nullable=False)

class MediaSidecar(db.Model):
    id = db.Column(BigInt, primary_key=True, autoincrement=True)
    media_id = db.Column(BigInt, db.ForeignKey('media.id'), nullable=False)
    type = db.Column(db.Enum('video', 'audio', 'subtitle', name='media_sidecar_type'), nullable=False)
    rel_path = db.Column(db.String(255))
    bytes = db.Column(BigInt)

class Exif(db.Model):
    media_id = db.Column(BigInt, db.ForeignKey('media.id'), primary_key=True)
    camera_make = db.Column(db.String(255))
    camera_model = db.Column(db.String(255))
    lens = db.Column(db.String(255))
    iso = db.Column(db.Integer)
    shutter = db.Column(db.String(32))
    f_number = db.Column(db.Numeric(5,2))
    focal_len = db.Column(db.Numeric(5,2))
    gps_lat = db.Column(db.Numeric(10,7))
    gps_lng = db.Column(db.Numeric(10,7))
    raw_json = db.Column(db.Text)

class Album(db.Model):
    id = db.Column(BigInt, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    cover_media_id = db.Column(BigInt, db.ForeignKey('media.id'))
    visibility = db.Column(db.Enum('public', 'private', 'unlisted', name='album_visibility'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), nullable=False)

class Tag(db.Model):
    id = db.Column(BigInt, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False)
    attr = db.Column(db.Enum('person', 'place', 'thing', name='tag_attr'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), nullable=False)
    created_by = db.Column(BigInt, db.ForeignKey('user.id'))
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), nullable=False)

class MediaPlayback(db.Model):
    id = db.Column(BigInt, primary_key=True, autoincrement=True)
    media_id = db.Column(BigInt, db.ForeignKey('media.id'), nullable=False)
    preset = db.Column(
        db.Enum('original', 'preview', 'mobile', 'std1080p', name='media_playback_preset'),
        nullable=False,
    )
    rel_path = db.Column(db.String(255))
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)
    v_codec = db.Column(db.String(32))
    a_codec = db.Column(db.String(32))
    v_bitrate_kbps = db.Column(db.Integer)
    duration_ms = db.Column(db.Integer)
    poster_rel_path = db.Column(db.String(255))
    hash_sha256 = db.Column(db.CHAR(64))
    status = db.Column(db.Enum('pending', 'processing', 'done', 'error', name='media_playback_status'), nullable=False)
    error_msg = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), nullable=False)

class MediaItem(db.Model):
    id = db.Column(db.String(255), primary_key=True)
    type = db.Column(
        db.Enum('TYPE_UNSPECIFIED', 'PHOTO', 'VIDEO', name='media_item_type'),
        nullable=False,
    )
    mime_type = db.Column(db.String(255))
    filename = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), nullable=False)
    media_file_metadata = db.relationship(
        'MediaFileMetadata',
        backref='media_item',
        cascade='all, delete-orphan',
        uselist=False,
    )


class PickedMediaItem(db.Model):
    id = db.Column(BigInt, primary_key=True, autoincrement=True)
    picker_session_id = db.Column(
        BigInt, db.ForeignKey('picker_session.id'), nullable=False
    )
    media_item_id = db.Column(
        db.String(255), db.ForeignKey('media_item.id'), nullable=False
    )
    status = db.Column(
        db.Enum(
            'pending', 'imported', 'dup', 'failed', 'expired', 'skipped',
            name='picked_media_item_status'
        ),
        nullable=False,
        default='pending',
        server_default='pending',
    )
    media_item = db.relationship(
        'MediaItem',
        backref=db.backref('picked_media_items', cascade='all, delete-orphan')
    )
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), nullable=False)
    __table_args__ = (
        db.UniqueConstraint('picker_session_id', 'media_item_id',
                            name='uq_picked_media_item_session_media'),
    )


class MediaFileMetadata(db.Model):
    id = db.Column(BigInt, primary_key=True, autoincrement=True)
    media_item_id = db.Column(
        db.String(255), db.ForeignKey('media_item.id'), nullable=False, unique=True
    )
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)
    camera_make = db.Column(db.String(255))
    camera_model = db.Column(db.String(255))
    photo_metadata_id = db.Column(BigInt, db.ForeignKey('photo_metadata.id'))
    video_metadata_id = db.Column(BigInt, db.ForeignKey('video_metadata.id'))
    photo_metadata = db.relationship('PhotoMetadata', backref='media_file_metadata', uselist=False)
    video_metadata = db.relationship('VideoMetadata', backref='media_file_metadata', uselist=False)


class PhotoMetadata(db.Model):
    id = db.Column(BigInt, primary_key=True, autoincrement=True)
    focal_length = db.Column(db.Float)
    aperture_f_number = db.Column(db.Float)
    iso_equivalent = db.Column(db.Integer)
    exposure_time = db.Column(db.String(32))


class VideoMetadata(db.Model):
    id = db.Column(BigInt, primary_key=True, autoincrement=True)
    fps = db.Column(db.Float)
    processing_status = db.Column(
        db.Enum('UNSPECIFIED', 'PROCESSING', 'READY', 'FAILED', name='video_processing_status')
    )

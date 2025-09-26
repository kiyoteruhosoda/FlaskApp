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
    
    # ソース情報
    source_type = db.Column(db.Enum('local', 'google_photos', name='media_source_type'), nullable=False, default='local')
    google_media_id = db.Column(db.String(255), nullable=True)  # Google Photos ID
    account_id = db.Column(BigInt, db.ForeignKey('google_account.id'), nullable=True)
    account = db.relationship('GoogleAccount', backref='media_items')
    
    # ファイル情報
    local_rel_path = db.Column(db.String(255), nullable=True)  # ローカルファイルパス
    filename = db.Column(db.String(255), nullable=True)  # 元のファイル名
    hash_sha256 = db.Column(db.CHAR(64), nullable=True)
    bytes = db.Column(BigInt, nullable=True)
    
    # メディア情報
    mime_type = db.Column(db.String(255))
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)
    duration_ms = db.Column(db.Integer, nullable=True)
    orientation = db.Column(db.Integer, nullable=True)
    is_video = db.Column(db.Boolean, default=False, nullable=False)
    
    # 撮影情報
    shot_at = db.Column(db.DateTime, nullable=True)
    camera_make = db.Column(db.String(255), nullable=True)
    camera_model = db.Column(db.String(255), nullable=True)
    
    # 管理情報
    imported_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), nullable=False)
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)
    has_playback = db.Column(db.Boolean, default=False, nullable=False)
    live_group_id = db.Column(BigInt, nullable=True)
    
    # タイムスタンプ
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc), nullable=False)
    
    # リレーション
    sidecars = db.relationship('MediaSidecar', backref='media', cascade='all, delete-orphan')
    exif = db.relationship('Exif', uselist=False, backref='media')
    albums = db.relationship('Album', secondary=album_item, backref='media')
    tags = db.relationship('Tag', secondary=media_tag, backref='media')
    playbacks = db.relationship('MediaPlayback', backref='media', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Media {self.id}: {self.source_type} - {self.filename or self.google_media_id}>'
    
    @property
    def display_name(self):
        """表示用の名前を返す（撮影日時ベース）"""
        if self.shot_at:
            return self.shot_at.strftime('%Y-%m-%d %H:%M')
        elif self.created_at:
            return f'Import {self.created_at.strftime("%Y-%m-%d %H:%M")}'
        else:
            return f'Media {self.id}'
    
    @property
    def is_local(self):
        return self.source_type == 'local'
    
    @property
    def is_google_photos(self):
        return self.source_type == 'google_photos'

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
    display_order = db.Column(db.Integer, nullable=True)
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
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)
    camera_make = db.Column(db.String(255))
    camera_model = db.Column(db.String(255))
    photo_metadata_id = db.Column(BigInt, db.ForeignKey('photo_metadata.id'))
    video_metadata_id = db.Column(BigInt, db.ForeignKey('video_metadata.id'))
    photo_metadata = db.relationship(
        'PhotoMetadata',
        backref='media_item',
        uselist=False,
        cascade='all, delete-orphan',
        single_parent=True,
    )
    video_metadata = db.relationship('VideoMetadata', backref='media_item', uselist=False)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), nullable=False)


class PickerSelection(db.Model):
    id = db.Column(BigInt, primary_key=True, autoincrement=True)
    session_id = db.Column(BigInt, db.ForeignKey('picker_session.id'), nullable=False)
    google_media_id = db.Column(
        db.String(255), db.ForeignKey('media_item.id'), nullable=True  # ローカルインポート用にNULL許可
    )
    local_file_path = db.Column(db.Text, nullable=True)  # ローカルインポート用ファイルパス
    local_filename = db.Column(db.String(500), nullable=True)  # ローカルインポート用ファイル名
    status = db.Column(
        db.Enum(
            'pending', 'enqueued', 'running', 'imported', 'dup',
            'failed', 'expired', 'skipped', name='picker_selection_status'
        ),
        nullable=False,
        default='pending',
        server_default='pending',
    )
    media_item = db.relationship(
        'MediaItem',
        backref=db.backref('picker_selections', cascade='all, delete-orphan')
    )
    create_time = db.Column(db.DateTime)
    enqueued_at = db.Column(db.DateTime)
    started_at = db.Column(db.DateTime)
    finished_at = db.Column(db.DateTime)
    attempts = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    error_msg = db.Column(db.Text)
    base_url = db.Column(db.Text)
    base_url_fetched_at = db.Column(db.DateTime)
    base_url_valid_until = db.Column(db.DateTime)
    locked_by = db.Column(db.String(255))
    lock_heartbeat_at = db.Column(db.DateTime)
    last_transition_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), nullable=False)
    __table_args__ = (
        db.UniqueConstraint('session_id', 'google_media_id',
                            name='uq_picker_selection_session_media'),
        db.Index('idx_picker_selection_session_status', 'session_id', 'status'),
        db.Index('idx_picker_selection_status_lock', 'status', 'lock_heartbeat_at'),
    )


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

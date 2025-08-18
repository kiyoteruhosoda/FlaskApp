# SQLAlchemy models for the ER diagram provided
# Each class represents a table in the database


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
    created_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime)

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
    created_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime)

class Tag(db.Model):
    id = db.Column(BigInt, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False)
    attr = db.Column(db.Enum('person', 'place', 'thing', name='tag_attr'), nullable=False)
    created_at = db.Column(db.DateTime)
    created_by = db.Column(BigInt, db.ForeignKey('user.id'))
    updated_at = db.Column(db.DateTime)

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
    created_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime)

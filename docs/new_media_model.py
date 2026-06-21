# 新しいMediaモデルの設計案
# ローカルファイルとGoogleフォトを統一的に扱う

from datetime import datetime, timezone
from core.db import db

BigInt = db.BigInteger().with_variant(db.Integer, "sqlite")

class Media(db.Model):
    """統一的なメディア情報テーブル"""
    id = db.Column(BigInt, primary_key=True, autoincrement=True)
    
    # ソース情報
    source_type = db.Column(db.Enum('local', 'google_photos', name='media_source_type'), nullable=False)
    google_media_id = db.Column(db.String(255), nullable=True)  # Google Photos ID
    google_account_id = db.Column(BigInt, db.ForeignKey('google_account.id'), nullable=True)
    
    # ファイル情報
    local_rel_path = db.Column(db.String(255), nullable=True)  # ローカルファイルパス
    filename = db.Column(db.String(255), nullable=True)  # 元のファイル名
    hash_sha256 = db.Column(db.CHAR(64), nullable=True)
    bytes = db.Column(BigInt, nullable=True)
    
    # メディア情報
    mime_type = db.Column(db.String(255))
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)
    duration_ms = db.Column(db.Integer, nullable=True)  # 動画の場合
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
    albums = db.relationship('Album', secondary='album_item', backref='media')
    tags = db.relationship('Tag', secondary='media_tag', backref='media')
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

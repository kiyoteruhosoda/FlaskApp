from datetime import datetime, timezone

from core.db import db
from core.models.photo_models import PickedMediaItem
from core.models.picker_session import PickerSession

BigInt = db.BigInteger().with_variant(db.Integer, "sqlite")


class PickerImportTask(db.Model):
    __tablename__ = "picker_import_task"

    id = db.Column(BigInt, primary_key=True, autoincrement=True)

    # セッションとアイテムを結ぶ“選択結果＋DL進捗”
    picker_session_id = db.Column(
        BigInt, db.ForeignKey("picker_session.id"), nullable=False
    )
    picked_media_item_id = db.Column(
        db.String(255), db.ForeignKey("picked_media_item.id"), nullable=False
    )

    # 進捗とリトライ管理
    status = db.Column(
        db.Enum("queued", "running", "succeeded", "failed", "skipped", "expired", "dup",
                name="picker_import_task_status"),
        nullable=False,
        default="queued",
        server_default="queued",
    )
    attempt_count = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    last_error_code = db.Column(db.String(100))
    last_error_message = db.Column(db.Text)

    # その取得時点のベースURL（任意・スナップショット）
    base_url_snapshot = db.Column(db.Text)

    # ページング等の状態（必要なら）
    cursor = db.Column(db.String(255))

    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        db.UniqueConstraint("picker_session_id", "picked_media_item_id",
                            name="uk_task_session_item"),
        db.Index("idx_task_session_status", "picker_session_id", "status"),
    )

# 便利リレーション（任意）
PickerSession.import_tasks = db.relationship(
    "PickerImportTask",
    backref="picker_session",
    cascade="all, delete-orphan",
    lazy="dynamic",
)
PickedMediaItem.import_tasks = db.relationship(
    "PickerImportTask",
    backref="picked_media_item",
    cascade="all, delete-orphan",
    lazy="dynamic",
)

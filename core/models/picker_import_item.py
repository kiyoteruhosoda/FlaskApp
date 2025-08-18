from datetime import datetime, timezone

from core.db import db

BigInt = db.BigInteger().with_variant(db.Integer, "sqlite")


class PickerImportItem(db.Model):
    __tablename__ = "picker_import_item"

    id = db.Column(BigInt, primary_key=True, autoincrement=True)
    picker_session_id = db.Column(
        BigInt, db.ForeignKey("picker_session.id"), nullable=False, index=True
    )
    media_item_id = db.Column(db.String(255), nullable=False)
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    __table_args__ = (
        db.UniqueConstraint(
            "picker_session_id", "media_item_id", name="uniq_picker_session_media"
        ),
    )

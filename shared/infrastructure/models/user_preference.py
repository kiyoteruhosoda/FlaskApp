"""ユーザーごとの設定を保持するキー・バリューストア。

各ユーザーが個別に設定できる値（例: スライドショーの表示秒数）を
``user_preference`` テーブルで管理する。値は JSON 文字列として格納する。
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from shared.kernel.database.db import db

BigInt = db.BigInteger().with_variant(db.Integer, "sqlite")


class UserPreference(db.Model):
    """ユーザー設定エントリ（1ユーザー × 1キー = 1行）。"""

    __tablename__ = "user_preference"
    __table_args__ = (
        UniqueConstraint("user_id", "key", name="uq_user_preference_user_key"),
    )

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInt, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(db.String(120), nullable=False)
    # JSON エンコードされた値（文字列・数値・bool など何でも格納できる）
    value_json: Mapped[str] = mapped_column(db.Text, nullable=False)

    # -----------------------------------------------------------------
    # キー定数（アプリで使用する既知キー）
    # -----------------------------------------------------------------
    KEY_SLIDESHOW_INTERVAL = "slideshow_interval"
    # 画面表示に用いるタイムゾーン（IANA 名、例 "Asia/Tokyo"）。
    # 空文字/未設定はブラウザのタイムゾーンにフォールバックする（表示層で判定）。
    KEY_TIMEZONE = "timezone"

    # デフォルト値マップ（未設定時に使用）。
    # timezone は既定値を持たせない（未設定＝ブラウザ検出に委ねる）ため含めない。
    DEFAULTS: dict[str, Any] = {
        KEY_SLIDESHOW_INTERVAL: 5,  # 秒
    }

    # -----------------------------------------------------------------
    # ヘルパ
    # -----------------------------------------------------------------

    @property
    def value(self) -> Any:
        """JSON から Python オブジェクトへデシリアライズした値を返す。"""
        return json.loads(self.value_json)

    @value.setter
    def value(self, v: Any) -> None:
        self.value_json = json.dumps(v, ensure_ascii=False)

    @classmethod
    def get_all_for_user(cls, user_id: int) -> dict[str, Any]:
        """ユーザーの全設定を ``{key: value}`` 形式で返す（デフォルト込み）。"""
        rows = cls.query.filter_by(user_id=user_id).all()
        result: dict[str, Any] = dict(cls.DEFAULTS)
        for row in rows:
            result[row.key] = row.value
        return result

    @classmethod
    def set_for_user(cls, user_id: int, key: str, value: Any) -> "UserPreference":
        """設定値をアップサート（なければ作成、あれば更新）する。"""
        row = cls.query.filter_by(user_id=user_id, key=key).first()
        if row is None:
            row = cls(user_id=user_id, key=key)
            db.session.add(row)
        row.value = value
        return row


__all__ = ["UserPreference"]

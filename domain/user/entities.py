from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Any
from werkzeug.security import generate_password_hash, check_password_hash


@dataclass
class User:
    email: str
    password_hash: str = field(init=False)
    totp_secret: Optional[str] = None
    id: Optional[int] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_active: bool = True
    _model: Any | None = field(default=None, repr=False, compare=False, init=False)

    def set_password(self, raw: str) -> None:
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw: str) -> bool:
        return check_password_hash(self.password_hash, raw)

    def attach_model(self, model: Any | None) -> None:
        """内部的に関連付けるORMモデルを設定する。"""
        self._model = model

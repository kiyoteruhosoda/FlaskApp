"""Dummy model used only for app initialisation in tests."""
from __future__ import annotations

from sqlalchemy.orm import Mapped, mapped_column

from core.db import db


class PickerImportTask(db.Model):
    __tablename__ = "picker_import_task"

    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)

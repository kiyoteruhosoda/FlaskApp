"""Dummy model used only for app initialisation in tests."""

from core.db import db


class PickerImportTask(db.Model):
    __tablename__ = "picker_import_task"

    id = db.Column(db.Integer, primary_key=True)

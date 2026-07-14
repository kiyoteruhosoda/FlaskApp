"""``ResolvedStorageFile`` の属性委譲に関する回帰テスト。

``presentation/fastapi/routers/media.py`` は解決結果に対して ``.exists`` /
``.absolute_path`` / ``.base_path`` を直接参照する。以前は ``ResolvedStorageFile``
がこれらを公開しておらず（解決結果を ``resolution`` フィールドに保持するのみ）、
``POST /api/media/{id}/thumb-url`` などが
``AttributeError: 'ResolvedStorageFile' object has no attribute 'exists'``
で 500 を返していた。
"""
from __future__ import annotations

from bounded_contexts.storage.infrastructure.filesystem import ResolvedPath
from presentation.fastapi.services.storage_helpers import ResolvedStorageFile


def test_resolved_storage_file_delegates_path_attributes() -> None:
    resolution = ResolvedPath(
        base_path="/srv/thumbs",
        absolute_path="/srv/thumbs/512/ab/cd.jpg",
        exists=True,
    )
    resolved = ResolvedStorageFile(
        selector="media_thumbnails",
        area=None,
        resolution=resolution,
    )

    assert resolved.exists is True
    assert resolved.absolute_path == "/srv/thumbs/512/ab/cd.jpg"
    assert resolved.base_path == "/srv/thumbs"


def test_resolved_storage_file_reports_missing_file() -> None:
    resolution = ResolvedPath(base_path=None, absolute_path=None, exists=False)
    resolved = ResolvedStorageFile(
        selector="media_thumbnails",
        area=None,
        resolution=resolution,
    )

    assert resolved.exists is False
    assert resolved.absolute_path is None
    assert resolved.base_path is None

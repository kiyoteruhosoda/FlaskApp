from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List

import pytest

from features.photonest.application.importing import ImportCommand
from features.photonest.application.importing.results import ImportResult
from features.photonest.application.importing.strategies.google import GoogleImporter
from features.photonest.domain.importing.factory import MediaFactory
from features.photonest.domain.importing.import_session import ImportSession
from features.photonest.domain.importing.media import Media
from features.photonest.domain.importing.media_hash import MediaHash
from features.photonest.domain.importing.services import ImportDomainService
from features.photonest.infrastructure.importing.google import (
    GoogleMediaClient,
    GoogleMediaItem,
)


class DummyLogger:
    def __getattr__(self, name):  # pragma: no cover - fallback
        def noop(*args, **kwargs):
            return None

        return noop

    def info(self, *args, **kwargs):
        return None

    def debug(self, *args, **kwargs):
        return None

    def exception(self, *args, **kwargs):
        return None


@dataclass
class FakeRepository:
    saved: Dict[str, Media]

    def __init__(self) -> None:
        self.saved = {}

    def exists_by_hash(self, media_hash: MediaHash) -> bool:
        return media_hash.value in self.saved

    def save_media(self, media: Media, session: ImportSession) -> None:
        self.saved[media.hash.value] = media


@dataclass
class FakeHasher:
    def normalize(self, media: Media) -> Media:
        return media


@dataclass
class StubGoogleClient(GoogleMediaClient):
    items: List[GoogleMediaItem]

    def list_media(self, account_id: str, *, page_size: int = 100) -> List[GoogleMediaItem]:
        return list(self.items)


@pytest.fixture
def google_media_item() -> GoogleMediaItem:
    return GoogleMediaItem(
        id="gm_1",
        filename="photo.jpg",
        mime_type="image/jpeg",
        size_bytes=512,
        width=640,
        height=480,
        duration_ms=None,
        shot_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
        download_url="https://example.com/photo.jpg",
        checksum="hash-gm-1",
        is_video=False,
    )


@pytest.fixture
def media_factory() -> MediaFactory:
    return MediaFactory()


@pytest.fixture
def domain_service() -> ImportDomainService:
    return ImportDomainService(media_repository=FakeRepository(), hasher=FakeHasher())


def test_google_importer_registers_media(
    google_media_item: GoogleMediaItem,
    media_factory: MediaFactory,
    domain_service: ImportDomainService,
) -> None:
    importer = GoogleImporter(
        client=StubGoogleClient([google_media_item]),
        media_factory=media_factory,
        domain_service=domain_service,
        logger=DummyLogger(),
    )

    command = ImportCommand(source="google", account_id="account-1")
    result = importer.execute(command)

    assert isinstance(result, ImportResult)
    assert result.imported_count == 1
    assert result.errors == []

    saved_media = domain_service.media_repository.saved  # type: ignore[attr-defined]
    assert "hash-gm-1" in saved_media
    assert saved_media["hash-gm-1"].extras.get("account_id") == "account-1"
    assert saved_media["hash-gm-1"].extras.get("google_media_id") == "gm_1"


def test_google_importer_marks_duplicates(
    google_media_item: GoogleMediaItem,
    media_factory: MediaFactory,
    domain_service: ImportDomainService,
) -> None:
    importer = GoogleImporter(
        client=StubGoogleClient([google_media_item]),
        media_factory=media_factory,
        domain_service=domain_service,
        logger=DummyLogger(),
    )

    command = ImportCommand(source="google", account_id="account-1")
    first_result = importer.execute(command)
    assert first_result.imported_count == 1

    duplicate_result = importer.execute(command)
    assert duplicate_result.duplicates_count == 1
    assert duplicate_result.imported_count == 0

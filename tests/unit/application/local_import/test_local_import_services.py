"""インポートアプリケーション層のテスト."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Dict, Iterable

import pytest

pytestmark = pytest.mark.unit  # アプリケーション層のユニットテスト

from bounded_contexts.photonest.application.importing import (
    ImportApplicationService,
    ImportCommand,
    ImportPolicy,
    LocalImporter,
)
from bounded_contexts.photonest.application.importing.results import ImportResult
from bounded_contexts.photonest.domain.importing.factory import MediaFactory
from bounded_contexts.photonest.domain.importing.import_session import ImportSession
from bounded_contexts.photonest.domain.importing.media import Media
from bounded_contexts.photonest.domain.importing.media_hash import MediaHash
from bounded_contexts.photonest.domain.importing.services import ImportDomainService
from bounded_contexts.photonest.domain.local_import.entities import ImportFile
from bounded_contexts.photonest.domain.local_import.media_file import MediaFileAnalysis
from bounded_contexts.photonest.infrastructure.importing.files import LocalFileRepository


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
class FakeAnalyzer:
    hash_value: str

    def analyze(self, file_path: str) -> MediaFileAnalysis:
        source = ImportFile(file_path)
        now = datetime.now(timezone.utc)
        return MediaFileAnalysis(
            source=source,
            extension=source.extension,
            file_size=10,
            file_hash=self.hash_value,
            mime_type="image/jpeg",
            is_video=False,
            width=100,
            height=100,
            duration_ms=None,
            orientation=None,
            shot_at=now,
            exif_data={},
            video_metadata={},
            destination_filename=source.name,
            relative_path=source.name,
            perceptual_hash="dummy",
        )


class FakeRepository:
    def __init__(self) -> None:
        self.saved: Dict[str, Media] = {}

    def exists_by_hash(self, media_hash: MediaHash) -> bool:
        return media_hash.value in self.saved

    def save_media(self, media: Media, session: ImportSession) -> None:
        self.saved[media.hash.value] = media


class FakeHasher:
    def normalize(self, media: Media) -> Media:
        return media


@pytest.fixture
def media_factory() -> MediaFactory:
    return MediaFactory(analyzer=FakeAnalyzer("hash"))


@pytest.fixture
def domain_service() -> ImportDomainService:
    return ImportDomainService(media_repository=FakeRepository(), hasher=FakeHasher())


@pytest.fixture
def local_importer(media_factory: MediaFactory, domain_service: ImportDomainService) -> LocalImporter:
    repository = LocalFileRepository(supported_extensions={".jpg"})
    return LocalImporter(
        file_repository=repository,
        media_factory=media_factory,
        domain_service=domain_service,
        logger=DummyLogger(),
    )


def test_local_importer_imports_files(tmp_path, local_importer: LocalImporter):
    (tmp_path / "image.jpg").write_bytes(b"data")
    command = ImportCommand(source="local", directory_path=str(tmp_path))

    result = local_importer.execute(command)

    assert isinstance(result, ImportResult)
    assert result.imported_count == 1
    assert result.duplicates_count == 0
    assert result.session_id is not None


def test_local_importer_detects_duplicates(tmp_path):
    (tmp_path / "image.jpg").write_bytes(b"data")
    factory = MediaFactory(analyzer=FakeAnalyzer("hash"))
    repository = FakeRepository()
    service = ImportDomainService(media_repository=repository, hasher=FakeHasher())
    importer = LocalImporter(
        file_repository=LocalFileRepository(supported_extensions={".jpg"}),
        media_factory=factory,
        domain_service=service,
        logger=DummyLogger(),
    )

    command = ImportCommand(source="local", directory_path=str(tmp_path))
    importer.execute(command)
    duplicate_result = importer.execute(command)

    assert duplicate_result.duplicates_count == 1
    assert duplicate_result.imported_count == 0


def test_import_policy_validates_directory(tmp_path):
    policy = ImportPolicy()
    command = ImportCommand(source="local", directory_path=str(tmp_path))
    policy.enforce(command)

    missing = ImportCommand(source="local", directory_path=str(tmp_path / "missing"))
    with pytest.raises(FileNotFoundError):
        policy.enforce(missing)


def test_application_service_dispatch(tmp_path):
    (tmp_path / "photo.jpg").write_bytes(b"data")
    importer = LocalImporter(
        file_repository=LocalFileRepository(supported_extensions={".jpg"}),
        media_factory=MediaFactory(analyzer=FakeAnalyzer("hash")),
        domain_service=ImportDomainService(
            media_repository=FakeRepository(),
            hasher=FakeHasher(),
        ),
        logger=DummyLogger(),
    )
    service = ImportApplicationService(
        policy=ImportPolicy(),
        importers={"local": importer},
        logger=DummyLogger(),
    )

    command = ImportCommand(source="local", directory_path=str(tmp_path))
    result = service.execute(command)

    assert result.imported_count == 1
    assert result.errors == []

"""新構造のテストヘルパーとユーティリティ."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from bounded_contexts.photonest.domain.local_import.value_objects import (
    FileHash,
    ImportStatus,
    RelativePath,
)
from bounded_contexts.photonest.domain.local_import.services import (
    MediaSignature,
    MediaDuplicateChecker,
)


# ===== テストデータビルダー =====


class MediaSignatureBuilder:
    """テスト用のMediaSignatureビルダー."""
    
    def __init__(self):
        self._sha256 = "a" * 64
        self._size = 1024
        self._phash = None
        self._shot_at = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        self._width = 1920
        self._height = 1080
        self._duration_ms = None
        self._is_video = False
    
    def with_hash(self, sha256: str, size: int, phash: Optional[str] = None):
        """ハッシュ値を設定."""
        self._sha256 = sha256
        self._size = size
        self._phash = phash
        return self
    
    def with_metadata(
        self,
        shot_at: datetime,
        width: int,
        height: int,
        duration_ms: Optional[int] = None,
    ):
        """メタデータを設定."""
        self._shot_at = shot_at
        self._width = width
        self._height = height
        self._duration_ms = duration_ms
        return self
    
    def as_video(self, duration_ms: int):
        """動画として設定."""
        self._is_video = True
        self._duration_ms = duration_ms
        return self
    
    def as_image(self):
        """画像として設定."""
        self._is_video = False
        self._duration_ms = None
        return self
    
    def build(self) -> MediaSignature:
        """MediaSignatureを構築."""
        file_hash = FileHash(
            sha256=self._sha256,
            size_bytes=self._size,
            perceptual_hash=self._phash,
        )
        return MediaSignature(
            file_hash=file_hash,
            shot_at=self._shot_at,
            width=self._width,
            height=self._height,
            duration_ms=self._duration_ms,
            is_video=self._is_video,
        )


class MockMedia:
    """テスト用のモックMediaエンティティ."""
    
    def __init__(
        self,
        id: int,
        hash_sha256: str,
        bytes: int,
        phash: Optional[str] = None,
        is_video: bool = False,
        shot_at: Optional[datetime] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        duration_ms: Optional[int] = None,
        is_deleted: bool = False,
    ):
        self.id = id
        self.hash_sha256 = hash_sha256
        self.bytes = bytes
        self.phash = phash
        self.is_video = is_video
        self.shot_at = shot_at
        self.width = width
        self.height = height
        self.duration_ms = duration_ms
        self.is_deleted = is_deleted


# ===== テストヘルパー関数 =====


def create_test_signature(
    *,
    hash_value: str = "a" * 64,
    size: int = 1024,
    phash: Optional[str] = None,
    is_video: bool = False,
) -> MediaSignature:
    """テスト用のMediaSignatureを簡単に作成."""
    builder = MediaSignatureBuilder()
    builder.with_hash(hash_value, size, phash)
    if is_video:
        builder.as_video(duration_ms=30000)
    else:
        builder.as_image()
    return builder.build()


def assert_signatures_match(sig1: MediaSignature, sig2: MediaSignature) -> bool:
    """2つのMediaSignatureが一致することを確認."""
    return (
        sig1.file_hash.sha256 == sig2.file_hash.sha256
        and sig1.file_hash.size_bytes == sig2.file_hash.size_bytes
        and sig1.shot_at == sig2.shot_at
        and sig1.width == sig2.width
        and sig1.height == sig2.height
        and sig1.is_video == sig2.is_video
    )


def test_duplicate_checker_with_candidates():
    """重複チェッカーの基本動作テスト."""
    # テストシグネチャ作成
    signature = create_test_signature(
        hash_value="abc123" + "0" * 58,
        size=2048,
        phash="phash123",
    )
    
    # モック候補を作成
    candidates = [
        MockMedia(
            id=1,
            hash_sha256="abc123" + "0" * 58,
            bytes=2048,
            phash="phash123",
            shot_at=datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            width=1920,
            height=1080,
        ),
        MockMedia(
            id=2,
            hash_sha256="def456" + "0" * 58,
            bytes=1024,
            phash="different",
            shot_at=datetime(2025, 1, 2, 0, 0, 0, tzinfo=timezone.utc),
            width=1280,
            height=720,
        ),
    ]
    
    # 重複チェック実行
    checker = MediaDuplicateChecker()
    result = checker.find_duplicate(signature, candidates)
    
    # 結果検証
    assert result is not None, "重複が検出されるべき"
    assert result.id == 1, "最初の候補が一致するはず"
    
    return True


def test_value_objects_immutability():
    """値オブジェクトの不変性テスト."""
    # FileHashの不変性
    file_hash = FileHash(sha256="a" * 64, size_bytes=1024, perceptual_hash="phash")
    
    try:
        file_hash.sha256 = "b" * 64  # type: ignore
        raise AssertionError("FileHashは不変であるべき")
    except AttributeError:
        pass  # 期待通り
    
    # ImportStatusの使用
    status = ImportStatus.IMPORTED
    assert status.is_successful()
    assert not status.is_error()
    assert status.is_terminal()
    
    # RelativePathの検証
    rel_path = RelativePath("2025/01/01/file.jpg")
    assert rel_path.value == "2025/01/01/file.jpg"
    assert rel_path.stem() == "file"
    assert rel_path.suffix() == ".jpg"
    
    # パストラバーサル攻撃の防止
    try:
        bad_path = RelativePath("../../../etc/passwd")
        raise AssertionError("パストラバーサルは防止されるべき")
    except ValueError:
        pass  # 期待通り
    
    return True


# ===== モンキーパッチヘルパー（既存テストとの互換性） =====


def enable_new_duplicate_checker():
    """新しい重複チェッカーを有効化（テスト用）."""
    from bounded_contexts.photonest.application.local_import import adapters
    adapters._USE_NEW_DUPLICATE_CHECKER = True


def disable_new_duplicate_checker():
    """旧重複チェッカーに戻す（テスト用）."""
    from bounded_contexts.photonest.application.local_import import adapters
    adapters._USE_NEW_DUPLICATE_CHECKER = False


def compare_implementations_on_test_data(analysis):
    """テストデータで新旧実装を比較."""
    from bounded_contexts.photonest.application.local_import.adapters import (
        compare_duplicate_checkers,
    )
    return compare_duplicate_checkers(analysis)

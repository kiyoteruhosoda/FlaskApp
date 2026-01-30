"""新構造のユニットテスト."""
from __future__ import annotations
import pytest
from datetime import datetime, timezone

pytestmark = pytest.mark.unit

from bounded_contexts.photonest.domain.local_import.value_objects import (
    FileHash,
    ImportStatus,
    RelativePath,
)
from bounded_contexts.photonest.domain.local_import.services import (
    MediaDuplicateChecker,
    MediaSignature,
    PathCalculator,
)
from tests.helpers.local_import_test_helpers import (
    MediaSignatureBuilder,
    MockMedia,
    create_test_signature,
)


class TestFileHash:
    """FileHash値オブジェクトのテスト."""
    
    def test_create_valid_hash(self):
        """正常なハッシュ値でインスタンス作成."""
        file_hash = FileHash(
            sha256="a" * 64,
            size_bytes=1024,
            perceptual_hash="phash123",
        )
        assert file_hash.sha256 == "a" * 64
        assert file_hash.size_bytes == 1024
        assert file_hash.perceptual_hash == "phash123"
    
    def test_invalid_sha256_length(self):
        """無効なSHA-256長でエラー."""
        with pytest.raises(ValueError, match="Invalid SHA-256"):
            FileHash(sha256="short", size_bytes=1024)
    
    def test_invalid_sha256_characters(self):
        """無効なSHA-256文字でエラー."""
        with pytest.raises(ValueError, match="hexadecimal"):
            FileHash(sha256="g" * 64, size_bytes=1024)
    
    def test_negative_size(self):
        """負のファイルサイズでエラー."""
        with pytest.raises(ValueError, match="cannot be negative"):
            FileHash(sha256="a" * 64, size_bytes=-1)
    
    def test_cryptographic_match(self):
        """暗号学的一致判定."""
        hash1 = FileHash(sha256="a" * 64, size_bytes=1024)
        hash2 = FileHash(sha256="a" * 64, size_bytes=1024)
        hash3 = FileHash(sha256="b" * 64, size_bytes=1024)
        
        assert hash1.matches_cryptographic(hash2)
        assert not hash1.matches_cryptographic(hash3)
    
    def test_perceptual_match(self):
        """知覚的一致判定."""
        hash1 = FileHash(sha256="a" * 64, size_bytes=1024, perceptual_hash="phash1")
        hash2 = FileHash(sha256="b" * 64, size_bytes=2048, perceptual_hash="phash1")
        hash3 = FileHash(sha256="c" * 64, size_bytes=1024, perceptual_hash="phash2")
        
        assert hash1.matches_perceptual(hash2)
        assert not hash1.matches_perceptual(hash3)


class TestImportStatus:
    """ImportStatus値オブジェクトのテスト."""
    
    def test_status_values(self):
        """ステータス値の確認."""
        assert ImportStatus.ENQUEUED.value == "enqueued"
        assert ImportStatus.IMPORTED.value == "imported"
        assert ImportStatus.DUPLICATE.value == "dup"
        assert ImportStatus.ERROR.value == "error"
    
    def test_is_terminal(self):
        """終端状態の判定."""
        assert ImportStatus.IMPORTED.is_terminal()
        assert ImportStatus.DUPLICATE.is_terminal()
        assert ImportStatus.CANCELLED.is_terminal()
        assert not ImportStatus.ENQUEUED.is_terminal()
        assert not ImportStatus.IMPORTING.is_terminal()
    
    def test_is_successful(self):
        """成功状態の判定."""
        assert ImportStatus.IMPORTED.is_successful()
        assert ImportStatus.DUPLICATE.is_successful()
        assert not ImportStatus.ERROR.is_successful()
        assert not ImportStatus.ENQUEUED.is_successful()
    
    def test_is_error(self):
        """エラー状態の判定."""
        assert ImportStatus.ERROR.is_error()
        assert not ImportStatus.IMPORTED.is_error()


class TestRelativePath:
    """RelativePath値オブジェクトのテスト."""
    
    def test_create_valid_path(self):
        """正常なパスでインスタンス作成."""
        rel_path = RelativePath("2025/01/01/file.jpg")
        assert rel_path.value == "2025/01/01/file.jpg"
    
    def test_prevent_path_traversal(self):
        """パストラバーサル攻撃の防止."""
        with pytest.raises(ValueError, match="cannot contain"):
            RelativePath("../../../etc/passwd")
    
    def test_reject_absolute_path(self):
        """絶対パスの拒否."""
        with pytest.raises(ValueError, match="must be relative"):
            RelativePath("/etc/passwd")
    
    def test_normalize_path(self):
        """パスの正規化."""
        rel_path = RelativePath("./2025/./01/./file.jpg")
        assert rel_path.value == "2025/01/file.jpg"
    
    def test_path_operations(self):
        """パス操作メソッド."""
        rel_path = RelativePath("2025/01/01/file.jpg")
        assert rel_path.stem() == "file"
        assert rel_path.suffix() == ".jpg"
        
        parent = rel_path.parent()
        assert parent.value == "2025/01/01"


class TestMediaDuplicateChecker:
    """MediaDuplicateCheckerドメインサービスのテスト."""
    
    def test_exact_match_with_phash(self):
        """pHash + メタデータ完全一致."""
        checker = MediaDuplicateChecker()
        
        signature = create_test_signature(
            hash_value="abc" + "0" * 61,
            size=1024,
            phash="phash123",
        )
        
        candidates = [
            MockMedia(
                id=1,
                hash_sha256="abc" + "0" * 61,
                bytes=1024,
                phash="phash123",
                shot_at=datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
                width=1920,
                height=1080,
            ),
        ]
        
        result = checker.find_duplicate(signature, candidates)
        assert result is not None
        assert result.id == 1
    
    def test_perceptual_match_without_exact_metadata(self):
        """pHashのみ一致（メタデータ不一致）."""
        checker = MediaDuplicateChecker()
        
        signature = MediaSignatureBuilder() \
            .with_hash("abc" + "0" * 61, 1024, "phash123") \
            .with_metadata(
                datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
                1920,
                1080,
            ) \
            .as_image() \
            .build()
        
        candidates = [
            MockMedia(
                id=1,
                hash_sha256="def" + "0" * 61,
                bytes=2048,
                phash="phash123",
                shot_at=datetime(2025, 1, 2, 0, 0, 0, tzinfo=timezone.utc),
                width=1280,
                height=720,
            ),
        ]
        
        result = checker.find_duplicate(signature, candidates)
        assert result is not None
        assert result.id == 1
    
    def test_cryptographic_match_without_phash(self):
        """SHA-256 + サイズ一致（pHashなし）."""
        checker = MediaDuplicateChecker()
        
        signature = create_test_signature(
            hash_value="abc" + "0" * 61,
            size=1024,
            phash=None,
        )
        
        candidates = [
            MockMedia(
                id=1,
                hash_sha256="abc" + "0" * 61,
                bytes=1024,
                phash=None,
            ),
        ]
        
        result = checker.find_duplicate(signature, candidates)
        assert result is not None
        assert result.id == 1
    
    def test_no_match(self):
        """一致なし."""
        checker = MediaDuplicateChecker()
        
        signature = create_test_signature(
            hash_value="abc" + "0" * 61,
            size=1024,
        )
        
        candidates = [
            MockMedia(
                id=1,
                hash_sha256="def" + "0" * 61,
                bytes=2048,
            ),
        ]
        
        result = checker.find_duplicate(signature, candidates)
        assert result is None
    
    def test_exclude_deleted_media(self):
        """削除済みメディアを除外."""
        checker = MediaDuplicateChecker()
        
        signature = create_test_signature(
            hash_value="abc" + "0" * 61,
            size=1024,
        )
        
        candidates = [
            MockMedia(
                id=1,
                hash_sha256="abc" + "0" * 61,
                bytes=1024,
                is_deleted=True,
            ),
        ]
        
        result = checker.find_duplicate(signature, candidates)
        assert result is None


class TestPathCalculator:
    """PathCalculatorドメインサービスのテスト."""
    
    def test_calculate_storage_path(self):
        """保存先パス計算."""
        calculator = PathCalculator()
        
        shot_at = datetime(2025, 1, 15, 12, 30, 45, tzinfo=timezone.utc)
        rel_path = calculator.calculate_storage_path(
            shot_at=shot_at,
            source_type="local",
            file_hash="a1b2c3d4" + "0" * 56,
            extension=".jpg",
        )
        
        assert rel_path.value == "2025/01/15/20250115_123045_local_a1b2c3d4.jpg"
    
    def test_calculate_storage_path_without_shot_at(self):
        """撮影日時なしのパス計算."""
        calculator = PathCalculator()
        
        rel_path = calculator.calculate_storage_path(
            shot_at=None,
            source_type="local",
            file_hash="a1b2c3d4" + "0" * 56,
            extension=".jpg",
        )
        
        # デフォルトは1970/01/01
        assert rel_path.value.startswith("1970/01/01/")
    
    def test_calculate_playback_path(self):
        """再生用ファイルパス計算."""
        calculator = PathCalculator()
        
        original = RelativePath("2025/01/15/20250115_123045_local_a1b2c3d4.mov")
        playback = calculator.calculate_playback_path(original)
        
        assert playback.value == "2025/01/15/20250115_123045_local_a1b2c3d4_play.mp4"

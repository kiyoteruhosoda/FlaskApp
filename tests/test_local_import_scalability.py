"""Local Import スケーラビリティテスト

大量ファイル処理時のJSON桁溢れ問題を検証します。
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import Mock, MagicMock

from features.photonest.infrastructure.local_import.audit_logger import (
    AuditLogger,
    AuditLogEntry,
    LogLevel,
    LogCategory,
)
from features.photonest.infrastructure.local_import.audit_log_repository import (
    AuditLogRepository,
)


class TestAuditLoggerScalability:
    """AuditLoggerのスケーラビリティテスト"""
    
    @pytest.fixture
    def mock_repo(self):
        """モックリポジトリ"""
        repo = Mock(spec=AuditLogRepository)
        repo.last_saved_entry = None
        
        def save_entry(entry):
            repo.last_saved_entry = entry
        
        repo.save = Mock(side_effect=save_entry)
        return repo
    
    @pytest.fixture
    def logger(self, mock_repo):
        """テスト用ロガー"""
        return AuditLogger(mock_repo)
    
    def test_small_details_pass_through(self, logger, mock_repo):
        """小さなdetailsはそのまま保存される"""
        entry = AuditLogEntry(
            message="テスト",
            details={"key": "value", "count": 123},
        )
        
        logger.log(entry)
        
        saved = mock_repo.last_saved_entry
        assert saved.details == {"key": "value", "count": 123}
    
    def test_large_array_truncated(self, logger, mock_repo):
        """大量の配列は切り詰められる"""
        # 10万件の配列を作成
        large_array = [f"/path/to/file_{i}.jpg" for i in range(100_000)]
        
        entry = AuditLogEntry(
            message="テスト",
            details={"file_paths": large_array},
        )
        
        logger.log(entry)
        
        saved = mock_repo.last_saved_entry
        
        # 切り詰められたことを確認
        assert saved.details["file_paths"]["_truncated"] is True
        assert saved.details["file_paths"]["_original_count"] == 100_000
        assert len(saved.details["file_paths"]["first_items"]) == 5
        assert len(saved.details["file_paths"]["last_items"]) == 5
    
    def test_multiple_arrays_truncated(self, logger, mock_repo):
        """複数の大きな配列がすべて切り詰められる"""
        entry = AuditLogEntry(
            message="テスト",
            details={
                "errors": [f"Error {i}" for i in range(50_000)],
                "warnings": [f"Warning {i}" for i in range(30_000)],
                "file_paths": [f"/file_{i}.jpg" for i in range(20_000)],
            },
        )
        
        logger.log(entry)
        
        saved = mock_repo.last_saved_entry
        
        # すべての配列が切り詰められたことを確認
        assert saved.details["errors"]["_truncated"] is True
        assert saved.details["warnings"]["_truncated"] is True
        assert saved.details["file_paths"]["_truncated"] is True
    
    def test_json_size_under_limit(self, logger, mock_repo):
        """JSONサイズが制限以内に収まる"""
        # 2MBのデータを作成
        large_data = {
            "data1": "x" * 1_000_000,
            "data2": "y" * 1_000_000,
        }
        
        entry = AuditLogEntry(
            message="テスト",
            details=large_data,
        )
        
        logger.log(entry)
        
        saved = mock_repo.last_saved_entry
        
        # サイズを確認
        json_str = json.dumps(saved.details, ensure_ascii=False)
        size_bytes = len(json_str.encode('utf-8'))
        
        assert size_bytes < 900_000, f"JSONサイズが制限超過: {size_bytes} bytes"
        assert saved.details["_truncated"] is True
        assert saved.details["_reason"] == "サイズ超過により詳細を省略"
    
    def test_nested_dict_truncated(self, logger, mock_repo):
        """ネストした辞書内の配列も切り詰められる"""
        entry = AuditLogEntry(
            message="テスト",
            details={
                "results": {
                    "errors": [f"Error {i}" for i in range(50_000)],
                    "successes": [f"Success {i}" for i in range(80_000)],
                },
            },
        )
        
        logger.log(entry)
        
        saved = mock_repo.last_saved_entry
        
        # ネストした配列が切り詰められたことを確認
        assert saved.details["results"]["errors"]["_truncated"] is True
        assert saved.details["results"]["successes"]["_truncated"] is True
    
    def test_recommended_actions_limited(self, logger, mock_repo):
        """推奨アクションが50件に制限される"""
        entry = AuditLogEntry(
            message="テスト",
            recommended_actions=[f"Action {i}" for i in range(200)],
        )
        
        logger.log(entry)
        
        saved = mock_repo.last_saved_entry
        
        # 50件＋省略メッセージ＝51件
        assert len(saved.recommended_actions) == 51
        assert "省略" in saved.recommended_actions[-1]
    
    def test_real_world_scenario_10k_files(self, logger, mock_repo):
        """実際のシナリオ: 1万ファイル処理"""
        # 1万ファイルの処理結果をシミュレート
        file_results = [
            {
                "path": f"/data/photos/2024/01/photo_{i:05d}.jpg",
                "size_bytes": 2_500_000 + (i % 1000) * 1000,
                "hash": f"sha256_{i:064x}",
                "status": "success" if i % 100 != 0 else "failed",
            }
            for i in range(10_000)
        ]
        
        entry = AuditLogEntry(
            message="1万ファイルのインポート完了",
            category=LogCategory.PERFORMANCE,
            details={
                "total_files": 10_000,
                "success": 9_900,
                "failed": 100,
                "file_results": file_results,  # ← これが大量データ
            },
        )
        
        logger.log(entry)
        
        saved = mock_repo.last_saved_entry
        
        # 配列が切り詰められたことを確認
        assert saved.details["file_results"]["_truncated"] is True
        assert saved.details["file_results"]["_original_count"] == 10_000
        
        # JSONサイズが制限以内
        json_str = json.dumps(saved.details, ensure_ascii=False)
        size_bytes = len(json_str.encode('utf-8'))
        assert size_bytes < 1_000_000, f"JSONサイズ: {size_bytes} bytes"
    
    def test_performance_large_truncation(self, logger, mock_repo):
        """パフォーマンステスト: 大量データの切り詰め"""
        import time
        
        # 10万件の配列
        large_data = [f"Item {i}" for i in range(100_000)]
        
        entry = AuditLogEntry(
            message="パフォーマンステスト",
            details={"items": large_data},
        )
        
        start = time.perf_counter()
        logger.log(entry)
        duration = (time.perf_counter() - start) * 1000
        
        # 切り詰め処理が100ms以内に完了すること
        assert duration < 100, f"切り詰めが遅すぎる: {duration:.2f}ms"
        
        # 切り詰められたことを確認
        saved = mock_repo.last_saved_entry
        assert saved.details["items"]["_truncated"] is True


class TestLocalImportUseCaseScalability:
    """LocalImportUseCaseのスケーラビリティテスト"""
    
    def test_error_summary_creation(self):
        """エラーサマリーが正しく作成される"""
        from features.photonest.application.local_import.use_case import (
            LocalImportUseCase,
        )
        from features.photonest.domain.local_import.import_result import (
            ImportTaskResult,
        )
        
        # モックの依存関係
        use_case = LocalImportUseCase(
            db=Mock(),
            logger=Mock(),
            session_service=Mock(),
            scanner=Mock(),
            queue_processor=Mock(),
        )
        
        # 大量のエラーを含む結果
        result = ImportTaskResult()
        result.failure_reasons = [
            f"FileNotFoundError: /path/to/file_{i}.jpg"
            for i in range(10_000)
        ]
        result.failure_reasons.extend([
            f"PermissionError: /path/to/file_{i}.jpg"
            for i in range(5_000)
        ])
        
        # エラーサマリーを作成
        summary = use_case._create_error_summary(result)
        
        # サマリーが正しい
        assert summary["total_errors"] == 15_000
        assert "FileNotFoundError" in summary["error_types"]
        assert "PermissionError" in summary["error_types"]
        assert len(summary["sample_errors"]) == 5  # 代表例のみ
        
        # JSONサイズが妥当
        json_str = json.dumps(summary, ensure_ascii=False)
        size_bytes = len(json_str.encode('utf-8'))
        assert size_bytes < 10_000, f"サマリーサイズ: {size_bytes} bytes"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

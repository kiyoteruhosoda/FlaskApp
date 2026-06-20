"""依存関係とインポートの検証スクリプト

実装したすべてのモジュールが正しくインポートできるか確認します。
"""

from __future__ import annotations

import sys
import traceback


def _check_import(module_path: str, description: str) -> tuple[bool, str]:
    """モジュールのインポートを検証する（pytest ケースではなく手動スクリプト用ヘルパ）。"""
    try:
        __import__(module_path)
        return True, f"✓ {description}"
    except Exception as e:
        error_msg = f"✗ {description}\n  エラー: {type(e).__name__}: {e}"
        return False, error_msg


def main():
    """すべてのインポートテストを実行"""
    
    tests = [
        # Domain層
        ("bounded_contexts.photonest.domain.local_import.state_machine", "Domain: State Machine"),
        
        # Application層
        ("bounded_contexts.photonest.application.local_import.state_synchronizer", "Application: State Synchronizer"),
        ("bounded_contexts.photonest.application.local_import.state_management_service", "Application: State Management Service"),
        ("bounded_contexts.photonest.application.local_import.troubleshooting", "Application: Troubleshooting Engine"),
        ("bounded_contexts.photonest.application.local_import.integration_example", "Application: Integration Example"),
        
        # Infrastructure層
        ("bounded_contexts.photonest.infrastructure.local_import.audit_logger", "Infrastructure: Audit Logger"),
        ("bounded_contexts.photonest.infrastructure.local_import.audit_log_repository", "Infrastructure: Audit Log Repository"),
        ("bounded_contexts.photonest.infrastructure.local_import.repositories", "Infrastructure: Repositories"),
        ("bounded_contexts.photonest.infrastructure.local_import.logging_integration", "Infrastructure: Logging Integration"),
        
        # Presentation層
        ("bounded_contexts.photonest.presentation.local_import_status_api", "Presentation: Status API"),
    ]
    
    print("=" * 80)
    print("Local Import状態管理システム - インポートテスト")
    print("=" * 80)
    print()
    
    results = []
    for module_path, description in tests:
        success, message = _check_import(module_path, description)
        results.append((success, message))
        print(message)
        if not success:
            print()
    
    print()
    print("=" * 80)
    
    total = len(results)
    passed = sum(1 for success, _ in results if success)
    failed = total - passed
    
    print(f"結果: {passed}/{total} 成功, {failed} 失敗")
    
    if failed > 0:
        print()
        print("⚠ インポートエラーが検出されました。")
        print("  - 依存モジュールが存在するか確認してください")
        print("  - 循環インポートがないか確認してください")
        return 1
    else:
        print()
        print("✓ すべてのモジュールが正常にインポートできました！")
        return 0


if __name__ == "__main__":
    sys.exit(main())

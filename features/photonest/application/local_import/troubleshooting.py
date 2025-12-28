"""Local Importトラブルシューティングシステム

エラー状況に応じた診断と推奨アクションを提供します。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ErrorSeverity(str, Enum):
    """エラーの深刻度"""
    
    LOW = "low"           # 警告レベル、処理続行可能
    MEDIUM = "medium"     # 一部失敗、他は続行可能
    HIGH = "high"         # 重要な失敗、要対応
    CRITICAL = "critical" # システムレベルの問題


class ErrorCategory(str, Enum):
    """エラーカテゴリ"""
    
    FILE_NOT_FOUND = "file_not_found"
    PERMISSION_DENIED = "permission_denied"
    DISK_SPACE = "disk_space"
    CORRUPT_FILE = "corrupt_file"
    DUPLICATE = "duplicate"
    INVALID_FORMAT = "invalid_format"
    DB_ERROR = "db_error"
    NETWORK_ERROR = "network_error"
    STATE_MISMATCH = "state_mismatch"
    UNKNOWN = "unknown"


@dataclass
class TroubleshootingResult:
    """トラブルシューティング結果"""
    
    category: ErrorCategory
    severity: ErrorSeverity
    summary: str
    diagnosis: str
    recommended_actions: list[str]
    related_docs: list[str]
    is_retryable: bool
    estimated_fix_time: str
    
    def to_dict(self) -> dict:
        """辞書に変換"""
        return {
            "category": self.category.value,
            "severity": self.severity.value,
            "summary": self.summary,
            "diagnosis": self.diagnosis,
            "recommended_actions": self.recommended_actions,
            "related_docs": self.related_docs,
            "is_retryable": self.is_retryable,
            "estimated_fix_time": self.estimated_fix_time,
        }


class TroubleshootingEngine:
    """トラブルシューティングエンジン
    
    エラーを分析し、適切な診断と推奨アクションを提供します。
    """
    
    def __init__(self):
        # エラーパターンと対処法のマッピング
        self._patterns = self._initialize_patterns()
    
    def diagnose(
        self,
        error: Exception,
        context: dict,
    ) -> TroubleshootingResult:
        """エラーを診断
        
        Args:
            error: 例外オブジェクト
            context: コンテキスト情報（file_path, operation等）
            
        Returns:
            TroubleshootingResult: 診断結果
        """
        error_type = type(error).__name__
        error_message = str(error)
        
        # エラータイプに基づいてパターンを検索
        for pattern in self._patterns:
            if pattern["error_type"] == error_type:
                return self._create_result(pattern, error, context)
        
        # パターンが見つからない場合は汎用的な結果を返す
        return self._create_unknown_result(error, context)
    
    def _create_result(
        self,
        pattern: dict,
        error: Exception,
        context: dict,
    ) -> TroubleshootingResult:
        """パターンから結果を作成"""
        file_path = context.get("file_path", "N/A")
        operation = context.get("operation", "処理")
        
        # 変数を埋め込み
        summary = pattern["summary"].format(
            operation=operation,
            file_path=file_path,
            error=error,
        )
        
        diagnosis = pattern["diagnosis"].format(
            operation=operation,
            file_path=file_path,
            error=error,
        )
        
        # アクションをコンテキストに応じてカスタマイズ
        actions = []
        for action_template in pattern["actions"]:
            action = action_template.format(
                file_path=file_path,
                operation=operation,
            )
            actions.append(action)
        
        return TroubleshootingResult(
            category=ErrorCategory(pattern["category"]),
            severity=ErrorSeverity(pattern["severity"]),
            summary=summary,
            diagnosis=diagnosis,
            recommended_actions=actions,
            related_docs=pattern.get("docs", []),
            is_retryable=pattern.get("retryable", False),
            estimated_fix_time=pattern.get("fix_time", "不明"),
        )
    
    def _create_unknown_result(
        self,
        error: Exception,
        context: dict,
    ) -> TroubleshootingResult:
        """不明なエラーの結果を作成"""
        return TroubleshootingResult(
            category=ErrorCategory.UNKNOWN,
            severity=ErrorSeverity.MEDIUM,
            summary=f"予期しないエラー: {type(error).__name__}",
            diagnosis=f"エラー詳細: {error}",
            recommended_actions=[
                "エラーメッセージとスタックトレースを確認",
                "ログファイルで前後の処理を確認",
                "同じ条件で再現するか確認",
                "必要に応じてサポートに連絡",
            ],
            related_docs=["docs/local_import_troubleshooting.md"],
            is_retryable=True,
            estimated_fix_time="状況による",
        )
    
    @staticmethod
    def _initialize_patterns() -> list[dict]:
        """エラーパターンを初期化"""
        return [
            # ファイルが見つからない
            {
                "error_type": "FileNotFoundError",
                "category": "file_not_found",
                "severity": "medium",
                "summary": "{operation}失敗: ファイルが見つかりません",
                "diagnosis": "ファイルパス '{file_path}' が存在しないか、アクセスできません。"
                           "ファイルが削除されたか、移動された可能性があります。",
                "actions": [
                    "ファイルの存在を確認: {file_path}",
                    "ファイルが移動・削除されていないか確認",
                    "パスの表記が正しいか確認（相対パス/絶対パス）",
                    "ディレクトリの権限を確認",
                    "別の場所にファイルがないか検索",
                ],
                "docs": [
                    "docs/local_import_troubleshooting.md#file-not-found",
                ],
                "retryable": False,
                "fix_time": "数分（ファイル確認）",
            },
            
            # 権限エラー
            {
                "error_type": "PermissionError",
                "category": "permission_denied",
                "severity": "high",
                "summary": "{operation}失敗: アクセス権限がありません",
                "diagnosis": "ファイルまたはディレクトリ '{file_path}' への読み書き権限がありません。",
                "actions": [
                    "ファイルの所有者とパーミッションを確認: ls -la {file_path}",
                    "実行ユーザーの権限を確認",
                    "chmod/chownでパーミッションを修正",
                    "他のプロセスがファイルをロックしていないか確認",
                    "SELinux/AppArmorの設定を確認（Linux）",
                ],
                "docs": [
                    "docs/local_import_troubleshooting.md#permission-denied",
                    "docs/synology-deployment.md#permissions",
                ],
                "retryable": False,
                "fix_time": "5-10分（権限修正）",
            },
            
            # ディスク容量不足
            {
                "error_type": "OSError",
                "category": "disk_space",
                "severity": "critical",
                "summary": "{operation}失敗: ディスク容量不足の可能性",
                "diagnosis": "ファイル操作中にOSErrorが発生しました。"
                           "ディスク容量不足またはファイルシステムの問題の可能性があります。",
                "actions": [
                    "ディスク容量を確認: df -h",
                    "不要なファイルを削除してスペースを確保",
                    "ファイルシステムのエラーをチェック",
                    "iノード使用率を確認: df -i",
                    "一時ファイルをクリーンアップ",
                ],
                "docs": [
                    "docs/local_import_troubleshooting.md#disk-space",
                    "docs/backup_cleanup.md",
                ],
                "retryable": True,
                "fix_time": "10-30分（容量確保）",
            },
            
            # 値エラー（無効な入力）
            {
                "error_type": "ValueError",
                "category": "invalid_format",
                "severity": "medium",
                "summary": "{operation}失敗: 無効なデータ形式",
                "diagnosis": "入力データまたはファイル形式が期待される形式と一致しません。",
                "actions": [
                    "ファイル形式を確認: file {file_path}",
                    "ファイルが破損していないか確認",
                    "メタデータの形式を確認",
                    "サポートされているファイル形式か確認",
                    "別のツールでファイルを検証",
                ],
                "docs": [
                    "docs/local_import_troubleshooting.md#invalid-format",
                ],
                "retryable": False,
                "fix_time": "数分（形式確認）",
            },
            
            # データベースエラー
            {
                "error_type": "IntegrityError",
                "category": "db_error",
                "severity": "high",
                "summary": "{operation}失敗: データベース整合性エラー",
                "diagnosis": "データベース制約違反が発生しました。"
                           "重複データまたは外部キー制約違反の可能性があります。",
                "actions": [
                    "重複するデータがないか確認",
                    "外部キー関係を確認",
                    "データベースの整合性をチェック",
                    "トランザクションログを確認",
                    "必要に応じてデータをクリーンアップ",
                ],
                "docs": [
                    "docs/local_import_troubleshooting.md#db-error",
                ],
                "retryable": False,
                "fix_time": "10-30分（データ確認・修正）",
            },
            
            # ネットワークエラー
            {
                "error_type": "ConnectionError",
                "category": "network_error",
                "severity": "medium",
                "summary": "{operation}失敗: ネットワーク接続エラー",
                "diagnosis": "外部サービスへの接続に失敗しました。",
                "actions": [
                    "ネットワーク接続を確認",
                    "外部サービスの状態を確認",
                    "ファイアウォール設定を確認",
                    "プロキシ設定を確認",
                    "数分待ってから再試行",
                ],
                "docs": [
                    "docs/local_import_troubleshooting.md#network-error",
                ],
                "retryable": True,
                "fix_time": "数分～数時間（ネットワーク復旧待ち）",
            },
        ]


class ActionRecommender:
    """推奨アクション生成器
    
    状況に応じた具体的なアクションを提案します。
    """
    
    @staticmethod
    def recommend_for_session_state(
        session_state: str,
        stats: dict,
    ) -> list[str]:
        """セッション状態に基づく推奨アクション
        
        Args:
            session_state: セッション状態
            stats: 統計情報
            
        Returns:
            list[str]: 推奨アクション
        """
        actions = []
        
        total = stats.get("total", 0)
        failed = stats.get("failed", 0)
        success = stats.get("success", 0)
        processing = stats.get("processing", 0)
        
        if session_state == "error":
            actions.extend([
                "エラーログを確認して根本原因を特定",
                "整合性チェックを実行",
                "必要に応じてセッションを再試行",
            ])
        
        elif session_state == "failed":
            failure_rate = failed / total if total > 0 else 0
            
            if failure_rate > 0.5:
                actions.extend([
                    f"失敗率が高い（{failure_rate:.1%}）ため、システム設定を確認",
                    "ディスク容量とパーミッションを確認",
                    "ログで共通のエラーパターンを確認",
                ])
            else:
                actions.extend([
                    f"{failed}個のアイテムが失敗しました",
                    "失敗したアイテムを個別に再処理",
                    "エラーログで失敗原因を確認",
                ])
        
        elif session_state == "processing" and processing == 0:
            actions.extend([
                "処理中状態ですが、アクティブなアイテムがありません",
                "セッション状態をIMPORTEDまたはFAILEDに更新",
                "整合性チェックを実行",
            ])
        
        elif session_state == "imported" and total > 0:
            success_rate = success / total if total > 0 else 0
            
            if success_rate < 1.0:
                actions.append(
                    f"成功率{success_rate:.1%}で完了（{failed}個失敗）"
                )
            else:
                actions.append(f"全{total}個のアイテムを正常にインポート")
        
        return actions
    
    @staticmethod
    def recommend_for_item_error(
        error_type: str,
        file_path: str,
    ) -> list[str]:
        """アイテムエラーに基づく推奨アクション
        
        Args:
            error_type: エラータイプ
            file_path: ファイルパス
            
        Returns:
            list[str]: 推奨アクション
        """
        actions = []
        
        if "NotFound" in error_type:
            actions.extend([
                f"ファイルの存在を確認: {file_path}",
                "ファイルが移動・削除されていないか確認",
                "元の場所にファイルを復元",
            ])
        
        elif "Permission" in error_type:
            actions.extend([
                f"ファイルのパーミッションを確認: {file_path}",
                "実行ユーザーの権限を確認",
                "必要に応じてchmod/chownで修正",
            ])
        
        elif "Integrity" in error_type or "Duplicate" in error_type:
            actions.extend([
                "既存の重複データを確認",
                "重複アイテムをスキップするか、既存データを更新",
            ])
        
        else:
            actions.extend([
                f"エラーログで詳細を確認: {error_type}",
                "ファイルの状態を手動で確認",
                "必要に応じて再試行",
            ])
        
        return actions


def generate_troubleshooting_report(
    session_id: int,
    session_state: str,
    errors: list[dict],
    stats: dict,
) -> dict:
    """トラブルシューティングレポートを生成
    
    Args:
        session_id: セッションID
        session_state: セッション状態
        errors: エラーログのリスト
        stats: 統計情報
        
    Returns:
        dict: レポート
    """
    # エラーを分類
    error_categories = {}
    for error in errors:
        category = error.get("category", "unknown")
        error_categories[category] = error_categories.get(category, 0) + 1
    
    # 推奨アクションを生成
    recommender = ActionRecommender()
    actions = recommender.recommend_for_session_state(session_state, stats)
    
    # 最も多いエラーカテゴリ
    top_error = max(error_categories.items(), key=lambda x: x[1]) if error_categories else None
    
    return {
        "session_id": session_id,
        "session_state": session_state,
        "total_errors": len(errors),
        "error_categories": error_categories,
        "top_error_category": top_error[0] if top_error else None,
        "recommended_actions": actions,
        "stats": stats,
        "severity": _determine_severity(error_categories, stats),
    }


def _determine_severity(error_categories: dict, stats: dict) -> str:
    """深刻度を判定"""
    total = stats.get("total", 0)
    failed = stats.get("failed", 0)
    
    if not total:
        return "low"
    
    failure_rate = failed / total
    
    if failure_rate > 0.8:
        return "critical"
    elif failure_rate > 0.5:
        return "high"
    elif failure_rate > 0.2:
        return "medium"
    else:
        return "low"

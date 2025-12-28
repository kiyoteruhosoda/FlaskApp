"""Local Import Phase 2/3統合サンプル

既存のlocal_import処理に状態管理とログシステムを統合する方法
"""

from __future__ import annotations

import time
from typing import Optional

from core.db import db
from features.photonest.domain.local_import.state_machine import ItemState, SessionState
from features.photonest.infrastructure.local_import.logging_integration import (
    get_structured_logger,
    log_duplicate_check,
    log_error_with_actions,
    log_file_operation,
    log_performance,
)
from features.photonest.infrastructure.local_import.repositories import (
    create_state_management_service,
)


# ============================================================
# Phase 2: 既存コードに状態遷移を追加
# ============================================================

def process_file_phase2(file_path: str, session_id: int) -> dict:
    """Phase 2: 状態遷移を追加した処理
    
    既存の処理フローに状態遷移とログを追加します。
    """
    item_id = f"item_{hash(file_path)}"
    
    # 状態管理サービスを取得
    state_mgr, audit_logger = create_state_management_service(db.session)
    
    # 構造化ログを取得
    logger = get_structured_logger(session_id, item_id)
    
    try:
        # PENDING → ANALYZING
        # state_mgr.transition_item(...) は現状未実装なので、ログのみ
        if logger:
            logger.info("ファイル処理開始", file_path=file_path)
        
        # ファイル解析
        start_time = time.perf_counter()
        analysis_result = analyze_file(file_path)
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        log_performance(
            "file_analysis",
            duration_ms,
            session_id=session_id,
            item_id=item_id,
            file_size_bytes=analysis_result.get("size"),
        )
        
        # 重複チェック
        if logger:
            logger.info("重複チェック開始")
        
        duplicate = check_duplicate(analysis_result)
        
        log_duplicate_check(
            "重複チェック完了",
            file_hash=analysis_result.get("hash", ""),
            match_type="exact" if duplicate else "none",
            session_id=session_id,
            item_id=item_id,
            is_duplicate=duplicate,
        )
        
        if duplicate:
            if logger:
                logger.info("重複のためスキップ")
            return {"status": "skipped", "reason": "duplicate"}
        
        # ファイル移動
        log_file_operation(
            "ファイル移動開始",
            file_path=file_path,
            operation="move",
            session_id=session_id,
            item_id=item_id,
        )
        
        move_result = move_file_to_storage(file_path, analysis_result)
        
        log_file_operation(
            "ファイル移動完了",
            file_path=move_result["new_path"],
            operation="move",
            session_id=session_id,
            item_id=item_id,
        )
        
        # DB更新
        if logger:
            logger.info("DB更新開始")
        
        save_to_database(analysis_result, move_result)
        
        if logger:
            logger.info("処理完了")
        
        return {"status": "imported"}
        
    except Exception as e:
        # エラーログと推奨アクション
        from features.photonest.application.local_import.troubleshooting import (
            TroubleshootingEngine,
        )
        
        engine = TroubleshootingEngine()
        result = engine.diagnose(e, {"file_path": file_path, "operation": "処理"})
        
        log_error_with_actions(
            f"処理失敗: {result.summary}",
            error=e,
            recommended_actions=result.recommended_actions,
            session_id=session_id,
            item_id=item_id,
        )
        
        return {"status": "failed", "error": str(e)}


# ============================================================
# Phase 3: with文による完全統合
# ============================================================

def process_file_phase3(file_path: str, session_id: int) -> dict:
    """Phase 3: with文による完全統合
    
    状態管理サービスのコンテキストマネージャを使用します。
    """
    item_id = f"item_{hash(file_path)}"
    
    # 状態管理サービスを取得
    state_mgr, _ = create_state_management_service(db.session)
    
    # with文でアイテム処理（自動的に状態遷移とログ記録）
    with state_mgr.process_item(item_id, file_path, session_id) as ctx:
        # 自動的に PENDING → ANALYZING に遷移
        
        # ファイル解析
        ctx.structured_logger.info("ファイル解析開始", file_size=get_file_size(file_path))
        
        from features.photonest.application.local_import.state_management_service import (
            PerformanceTracker,
        )
        
        tracker = PerformanceTracker(ctx.structured_logger)
        
        with tracker.measure("file_analysis", file_size_bytes=get_file_size(file_path)):
            analysis_result = analyze_file(file_path)
        
        # 重複チェック
        state_mgr.transition_item(ctx, ItemState.CHECKING, "重複チェック開始")
        
        with tracker.measure("duplicate_check"):
            duplicate = check_duplicate(analysis_result)
        
        if duplicate:
            state_mgr.transition_item(ctx, ItemState.SKIPPED, "重複のためスキップ")
            return {"status": "skipped", "reason": "duplicate"}
        
        # ファイル移動
        state_mgr.transition_item(ctx, ItemState.MOVING, "ファイル移動開始")
        
        with tracker.measure("file_move", file_size_bytes=get_file_size(file_path)):
            move_result = move_file_to_storage(file_path, analysis_result)
        
        # DB更新
        state_mgr.transition_item(ctx, ItemState.UPDATING, "DB更新開始")
        
        with tracker.measure("db_update"):
            save_to_database(analysis_result, move_result)
        
        # 自動的に IMPORTED に遷移してコミット
        # エラー時は自動的に FAILED に遷移
        
        return {"status": "imported"}


# ============================================================
# セッション全体の処理
# ============================================================

def process_session_with_state_management(session_id: int, file_paths: list[str]) -> dict:
    """セッション全体の処理（状態管理統合版）
    
    Args:
        session_id: セッションID
        file_paths: 処理するファイルパスのリスト
        
    Returns:
        dict: 処理結果
    """
    state_mgr, _ = create_state_management_service(db.session)
    
    # セッション開始
    state_mgr.transition_session(
        session_id,
        SessionState.PROCESSING,
        reason=f"{len(file_paths)}個のファイルを処理開始",
    )
    
    results = []
    
    for file_path in file_paths:
        try:
            # Phase 3の処理を使用
            result = process_file_phase3(file_path, session_id)
            results.append(result)
        except Exception as e:
            print(f"ファイル処理失敗: {file_path}, エラー: {e}")
            results.append({"status": "failed", "file": file_path})
    
    # セッション状態を自動同期
    snapshot = state_mgr.get_session_snapshot(session_id)
    
    # 結果に応じてセッション状態を遷移
    if snapshot.failed_count == 0:
        state_mgr.transition_session(
            session_id,
            SessionState.IMPORTED,
            reason="全ファイル処理完了",
        )
    elif snapshot.success_count > snapshot.failed_count:
        state_mgr.transition_session(
            session_id,
            SessionState.IMPORTED,
            reason=f"処理完了（成功: {snapshot.success_count}, 失敗: {snapshot.failed_count}）",
        )
    else:
        state_mgr.transition_session(
            session_id,
            SessionState.FAILED,
            reason=f"多数の失敗（成功: {snapshot.success_count}, 失敗: {snapshot.failed_count}）",
        )
    
    return {
        "session_id": session_id,
        "total": len(file_paths),
        "success": snapshot.success_count,
        "failed": snapshot.failed_count,
        "results": results,
    }


# ============================================================
# ダミー関数（既存コードのプレースホルダ）
# ============================================================

def analyze_file(file_path: str) -> dict:
    """ファイル解析（既存実装）"""
    import os
    return {
        "path": file_path,
        "size": os.path.getsize(file_path) if os.path.exists(file_path) else 0,
        "hash": "dummy_hash",
    }


def check_duplicate(analysis: dict) -> bool:
    """重複チェック（既存実装）"""
    return False


def move_file_to_storage(file_path: str, analysis: dict) -> dict:
    """ファイル移動（既存実装）"""
    return {"new_path": f"/storage/{analysis['hash']}.jpg"}


def save_to_database(analysis: dict, move_result: dict) -> None:
    """DB保存（既存実装）"""
    pass


def get_file_size(file_path: str) -> int:
    """ファイルサイズ取得"""
    import os
    return os.path.getsize(file_path) if os.path.exists(file_path) else 0

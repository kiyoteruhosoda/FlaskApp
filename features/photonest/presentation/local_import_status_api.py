"""Local Import状態管理API

セッション状態、エラーログ、トラブルシューティング情報を提供するAPIエンドポイント
"""

from __future__ import annotations

from flask import jsonify
from flask_smorest import abort, Blueprint
from marshmallow import Schema, fields

from core.db import db
from core.models.picker_session import PickerSession
from features.photonest.infrastructure.local_import.audit_log_repository import (
    AuditLogRepository,
    LogCategory,
    LogLevel,
)
from features.photonest.infrastructure.local_import.state_repositories import (
    create_state_management_service,
)
from features.photonest.application.local_import.troubleshooting import (
    generate_troubleshooting_report,
)

bp = Blueprint(
    "local_import_status",
    __name__,
    url_prefix="/api/local-import",
    description="Local Import状態管理API",
)


# Schemas
class SessionStatusSchema(Schema):
    """セッション状態スキーマ"""
    
    session_id = fields.Int(required=True)
    state = fields.Str(required=True)
    stats = fields.Dict(required=True)
    last_updated = fields.DateTime(required=True)


class ErrorLogSchema(Schema):
    """エラーログスキーマ"""
    
    id = fields.Int(required=True)
    timestamp = fields.DateTime(required=True)
    message = fields.Str(required=True)
    error_type = fields.Str(allow_none=True)
    error_message = fields.Str(allow_none=True)
    recommended_actions = fields.List(fields.Str(), allow_none=True)
    item_id = fields.Str(allow_none=True)


class StateTransitionSchema(Schema):
    """状態遷移スキーマ"""
    
    timestamp = fields.DateTime(required=True)
    from_state = fields.Str(required=True)
    to_state = fields.Str(required=True)
    reason = fields.Str(allow_none=True)


class ConsistencyCheckSchema(Schema):
    """整合性チェック結果スキーマ"""
    
    is_consistent = fields.Bool(required=True)
    session_state = fields.Str(required=True)
    issues = fields.List(fields.Str(), required=True)
    recommendations = fields.List(fields.Str(), required=True)


class TroubleshootingReportSchema(Schema):
    """トラブルシューティングレポートスキーマ"""
    
    session_id = fields.Int(required=True)
    session_state = fields.Str(required=True)
    total_errors = fields.Int(required=True)
    error_categories = fields.Dict(required=True)
    top_error_category = fields.Str(allow_none=True)
    recommended_actions = fields.List(fields.Str(), required=True)
    severity = fields.Str(required=True)


class PerformanceMetricSchema(Schema):
    """パフォーマンスメトリクススキーマ"""
    
    timestamp = fields.DateTime(required=True)
    operation_name = fields.Str(required=True)
    duration_ms = fields.Float(required=True)
    throughput_mbps = fields.Float(allow_none=True)


# Endpoints
@bp.get("/sessions/<int:session_id>/status")
def get_session_status(session_id: int):
    """セッション状態を取得
    
    Args:
        session_id: セッションID
        
    Returns:
        セッション状態情報
    """
    session = db.session.get(PickerSession, session_id)
    if not session:
        abort(404, message=f"セッションが見つかりません: {session_id}")
    
    stats = session.stats()
    
    return jsonify({
        "session_id": session_id,
        "state": session.status,
        "stats": stats,
        "last_updated": session.updated_at.isoformat(),
        "created_at": session.created_at.isoformat(),
    })


@bp.get("/sessions/<int:session_id>/errors")
def get_session_errors(session_id: int):
    """セッションのエラーログを取得
    
    Args:
        session_id: セッションID
        
    Returns:
        エラーログのリスト
    """
    repo = AuditLogRepository(db.session)
    errors = repo.get_errors(session_id=session_id, limit=100)
    
    return jsonify({
        "session_id": session_id,
        "total_count": len(errors),
        "errors": [
            {
                "id": log.id,
                "timestamp": log.timestamp.isoformat(),
                "message": log.message,
                "error_type": log.error_type,
                "error_message": log.error_message,
                "recommended_actions": log.recommended_actions or [],
                "item_id": log.item_id,
                "details": log.details,
            }
            for log in errors
        ],
    })


@bp.get("/sessions/<int:session_id>/transitions")
def get_state_transitions(session_id: int):
    """状態遷移履歴を取得
    
    Args:
        session_id: セッションID
        
    Returns:
        状態遷移履歴
    """
    repo = AuditLogRepository(db.session)
    transitions = repo.get_state_transitions(session_id)
    
    return jsonify({
        "session_id": session_id,
        "total_count": len(transitions),
        "transitions": [
            {
                "timestamp": log.timestamp.isoformat(),
                "from_state": log.from_state,
                "to_state": log.to_state,
                "reason": log.details.get("reason") if log.details else None,
                "item_id": log.item_id,
            }
            for log in transitions
        ],
    })


@bp.get("/sessions/<int:session_id>/consistency-check")
def check_consistency(session_id: int):
    """整合性チェックを実行
    
    Args:
        session_id: セッションID
        
    Returns:
        整合性チェック結果
    """
    try:
        state_mgr, _ = create_state_management_service(db.session)
        result = state_mgr.validate_consistency(session_id)
        
        return jsonify(result)
    except Exception as e:
        abort(500, message=f"整合性チェックに失敗: {str(e)}")


@bp.get("/sessions/<int:session_id>/troubleshooting")
def get_troubleshooting_report(session_id: int):
    """トラブルシューティングレポートを取得
    
    Args:
        session_id: セッションID
        
    Returns:
        トラブルシューティング情報
    """
    session = db.session.get(PickerSession, session_id)
    if not session:
        abort(404, message=f"セッションが見つかりません: {session_id}")
    
    repo = AuditLogRepository(db.session)
    errors = repo.get_errors(session_id=session_id, limit=100)
    stats = session.stats()
    
    report = generate_troubleshooting_report(
        session_id=session_id,
        session_state=session.status,
        errors=[log.to_dict() for log in errors],
        stats=stats,
    )
    
    return jsonify(report)


@bp.get("/sessions/<int:session_id>/performance")
def get_performance_metrics(session_id: int):
    """パフォーマンスメトリクスを取得
    
    Args:
        session_id: セッションID
        
    Returns:
        パフォーマンス情報
    """
    repo = AuditLogRepository(db.session)
    metrics = repo.get_performance_metrics(session_id)
    
    # 統計を計算
    total_duration = sum(log.duration_ms for log in metrics if log.duration_ms)
    avg_duration = total_duration / len(metrics) if metrics else 0
    
    return jsonify({
        "session_id": session_id,
        "total_operations": len(metrics),
        "total_duration_ms": total_duration,
        "avg_duration_ms": avg_duration,
        "metrics": [
            {
                "timestamp": log.timestamp.isoformat(),
                "operation_name": log.details.get("operation_name") if log.details else None,
                "duration_ms": log.duration_ms,
                "file_size_bytes": log.details.get("file_size_bytes") if log.details else None,
                "throughput_mbps": log.details.get("throughput_mbps") if log.details else None,
            }
            for log in metrics
        ],
    })


@bp.get("/sessions/<int:session_id>/logs")
def get_all_logs(session_id: int):
    """全ログを取得（カテゴリフィルタ可能）
    
    Args:
        session_id: セッションID
        
    Query Parameters:
        category: ログカテゴリフィルタ
        level: ログレベルフィルタ
        limit: 取得件数上限（デフォルト100）
        
    Returns:
        ログのリスト
    """
    from flask import request
    
    category = request.args.get("category")
    level = request.args.get("level")
    limit = int(request.args.get("limit", 100))
    
    repo = AuditLogRepository(db.session)
    
    # カテゴリとレベルを変換
    log_category = LogCategory(category) if category else None
    log_level = LogLevel(level) if level else None
    
    logs = repo.get_by_session(
        session_id=session_id,
        limit=limit,
        level=log_level,
        category=log_category,
    )
    
    return jsonify({
        "session_id": session_id,
        "total_count": len(logs),
        "filters": {
            "category": category,
            "level": level,
            "limit": limit,
        },
        "logs": [log.to_dict() for log in logs],
    })


@bp.get("/items/<string:item_id>/logs")
def get_item_logs(item_id: str):
    """アイテムのログを取得
    
    Args:
        item_id: アイテムID
        
    Returns:
        アイテムのログ
    """
    repo = AuditLogRepository(db.session)
    logs = repo.get_by_item(item_id, limit=50)
    
    return jsonify({
        "item_id": item_id,
        "total_count": len(logs),
        "logs": [log.to_dict() for log in logs],
    })

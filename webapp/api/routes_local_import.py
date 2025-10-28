from __future__ import annotations

from flask import jsonify, request
from flask_babel import gettext as _
from datetime import datetime, timezone
from typing import Any
import os

from core.settings import settings
from core.models.photo_models import PickerSelection
from core.models.picker_session import PickerSession
from ..extensions import db
from . import bp
from .openapi import json_request_body
from .routes import (
    _local_import_log,
    _storage_path,
    _storage_path_candidates,
    _storage_service,
    get_current_user,
    login_or_jwt_required,
)
@bp.post("/sync/local-import")
@login_or_jwt_required
@bp.doc(
    methods=["POST"],
    requestBody=json_request_body(
        "Trigger the local import worker.",
        required=False,
        schema={
            "type": "object",
            "properties": {
                "duplicateRegeneration": {
                    "type": "string",
                    "enum": ["regenerate", "skip"],
                    "description": "Controls how duplicate media should be handled.",
                }
            },
            "additionalProperties": False,
        },
        example={"duplicateRegeneration": "regenerate"},
    ),
)
def trigger_local_import():
    """ローカルファイル取り込みを手動実行"""
    user = get_current_user()
    if not user or not getattr(user, "can", None) or not user.can("system:manage"):
        _local_import_log(
            "Local import trigger rejected: insufficient permissions",
            level="warning",
            event="local_import.api.trigger",
            stage="denied",
        )
        return (
            jsonify({"error": _("You do not have permission to start a local import.")}),
            403,
        )

    from cli.src.celery.tasks import local_import_task_celery
    from core.models.picker_session import PickerSession
    from core.db import db
    import uuid
    import random
    import string

    payload = request.get_json(silent=True) or {}
    duplicate_regeneration = payload.get("duplicateRegeneration")
    if isinstance(duplicate_regeneration, str):
        duplicate_regeneration = duplicate_regeneration.lower()
    else:
        duplicate_regeneration = "regenerate"
    if duplicate_regeneration not in {"regenerate", "skip"}:
        duplicate_regeneration = "regenerate"

    _local_import_log(
        "Local import trigger requested",
        event="local_import.api.trigger",
        stage="start",
        duplicate_regeneration=duplicate_regeneration,
    )

    try:
        # PickerSessionを先に作成
        now = datetime.now(timezone.utc)
        random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
        session_id = f"local_import_{now.strftime('%Y%m%d_%H%M%S')}_{now.microsecond}_{random_suffix}"
        
        session = PickerSession(
            account_id=None,  # ローカルインポートの場合はNone
            session_id=session_id,
            status="processing",
            selected_count=0,
            created_at=now,
            updated_at=now,
            last_progress_at=now
        )
        stats = session.stats() if hasattr(session, "stats") else {}
        if not isinstance(stats, dict):
            stats = {}
        options = stats.get("options")
        if not isinstance(options, dict):
            options = {}
        options["duplicateRegeneration"] = duplicate_regeneration
        stats["options"] = options
        session.set_stats(stats)
        db.session.add(session)
        db.session.commit()

        # Celeryタスクにセッション情報を渡して非同期実行
        task = local_import_task_celery.delay(session_id)

        _local_import_log(
            "Local import task dispatched",
            event="local_import.api.trigger",
            stage="dispatched",
            session_id=session_id,
            celery_task_id=task.id,
            picker_session_db_id=session.id,
            duplicate_regeneration=duplicate_regeneration,
        )

        return jsonify({
            "success": True,
            "task_id": task.id,
            "session_id": session_id,
            "message": "ローカルインポートタスクを開始しました",
            "server_time": now.isoformat(),
            "duplicateRegeneration": duplicate_regeneration,
        })

    except Exception as e:
        _local_import_log(
            "Failed to start local import task",
            level="error",
            event="local_import.api.trigger",
            stage="error",
            error=str(e),
        )
        return jsonify({
            "success": False,
            "error": str(e),
            "server_time": datetime.now(timezone.utc).isoformat()
        }), 500


@bp.post("/sync/local-import/<path:session_id>/stop")
@login_or_jwt_required
def stop_local_import(session_id):
    """キャンセル要求を受けてローカルインポートを停止（管理者専用）。"""

    user = get_current_user()
    if not user or not getattr(user, "can", None) or not user.can("system:manage"):
        _local_import_log(
            "Local import stop rejected: insufficient permissions",
            level="warning",
            event="local_import.api.stop",
            stage="denied",
            session_id=session_id,
        )
        return (
            jsonify({"error": _("You do not have permission to stop a local import.")}),
            403,
        )

    _local_import_log(
        "Local import stop requested",
        event="local_import.api.stop",
        stage="start",
        session_id=session_id,
    )

    picker_session = (
        PickerSession.query.filter_by(session_id=session_id, account_id=None).first()
    )
    if not picker_session:
        _local_import_log(
            "Local import stop failed: session not found",
            level="warning",
            event="local_import.api.stop",
            stage="not_found",
            session_id=session_id,
        )
        return jsonify({"error": _("Local import session not found.")}), 404

    cancelable_statuses = {"expanding", "processing", "importing", "enqueued"}
    if picker_session.status == "canceled":
        _local_import_log(
            "Local import stop noop: already canceled",
            event="local_import.api.stop",
            stage="already_canceled",
            session_id=session_id,
        )
        return jsonify({"success": True, "message": _("Local import session is already canceled."), "session_id": session_id})

    if picker_session.status not in cancelable_statuses:
        _local_import_log(
            "Local import stop rejected: invalid status",
            level="warning",
            event="local_import.api.stop",
            stage="invalid_status",
            session_id=session_id,
            status=picker_session.status,
        )
        return (
            jsonify({"error": _("Local import session is not currently running.")}),
            409,
        )

    now = datetime.now(timezone.utc)

    stats = picker_session.stats() if hasattr(picker_session, "stats") else {}
    if not isinstance(stats, dict):
        stats = {}

    celery_task_id = stats.get("celery_task_id")

    pending_statuses = ("pending", "enqueued")
    skipped_items = (
        db.session.query(PickerSelection)
        .filter(
            PickerSelection.session_id == picker_session.id,
            PickerSelection.status.in_(pending_statuses),
        )
        .all()
    )

    skipped_count = 0
    for selection in skipped_items:
        selection.status = "skipped"
        selection.finished_at = now
        skipped_count += 1

    picker_session.status = "canceled"
    picker_session.updated_at = now
    picker_session.last_progress_at = now

    db.session.flush()

    counts_query = (
        db.session.query(
            PickerSelection.status,
            db.func.count(PickerSelection.id)
        )
        .filter(PickerSelection.session_id == picker_session.id)
        .group_by(PickerSelection.status)
        .all()
    )
    counts_map = {row[0]: row[1] for row in counts_query}

    pending_remaining = sum(
        counts_map.get(status, 0) for status in ("pending", "enqueued", "running")
    )
    imported_count = counts_map.get("imported", 0)
    dup_count = counts_map.get("dup", 0)
    skipped_total = counts_map.get("skipped", 0) + dup_count
    failed_count = counts_map.get("failed", 0)

    picker_session.selected_count = imported_count

    stats.update(
        {
            "stage": "canceling",
            "cancel_requested": True,
            "canceled_at": now.isoformat().replace("+00:00", "Z"),
            "total": imported_count + skipped_total + failed_count,
            "success": imported_count,
            "skipped": skipped_total,
            "failed": failed_count,
            "pending": pending_remaining,
        }
    )
    picker_session.set_stats(stats)

    db.session.commit()

    _local_import_log(
        "Local import stop marked",
        event="local_import.api.stop",
        stage="marked",
        session_id=session_id,
        celery_task_id=celery_task_id,
        skipped=skipped_count,
    )

    revoke_error = None
    if celery_task_id:
        try:
            from cli.src.celery.celery_app import celery

            celery.control.revoke(celery_task_id, terminate=False)
            _local_import_log(
                "Local import stop revoke dispatched",
                event="local_import.api.stop",
                stage="revoked",
                session_id=session_id,
                celery_task_id=celery_task_id,
            )
        except Exception as exc:
            revoke_error = str(exc)
            _local_import_log(
                "Local import stop revoke failed",
                level="error",
                event="local_import.api.stop",
                stage="revoke_failed",
                session_id=session_id,
                celery_task_id=celery_task_id,
                error=revoke_error,
            )

    payload = {
        "success": True,
        "session_id": session_id,
        "celery_task_id": celery_task_id,
        "skipped": skipped_count,
        "counts": {
            "imported": imported_count,
            "skipped": skipped_total,
            "failed": failed_count,
            "pending": pending_remaining,
        },
        "message": _("Local import session was canceled."),
    }

    if revoke_error:
        payload["revoke_error"] = revoke_error

    return jsonify(payload)


def _prepare_local_import_path(path_value):
    if not path_value:
        return {
            "raw": None,
            "absolute": None,
            "realpath": None,
            "exists": False,
        }

    service = _storage_service()
    raw_path = os.fspath(path_value)
    if "://" in raw_path:
        absolute = raw_path
        realpath = raw_path
    else:
        absolute = os.path.abspath(raw_path)
        try:
            realpath = os.path.realpath(absolute)
        except OSError:
            realpath = absolute
    exists = service.exists(realpath)
    return {
        "raw": path_value,
        "absolute": absolute,
        "realpath": realpath,
        "exists": exists,
    }


def _resolve_local_import_config():
    from webapp.config import BaseApplicationSettings

    directory_specs = [
        ("MEDIA_LOCAL_IMPORT_DIRECTORY", "import", settings.local_import_directory_configured),
        (
            "MEDIA_NAS_ORIGINALS_DIRECTORY",
            "originals",
            settings.nas_originals_directory_configured,
        ),
        (
            "MEDIA_NAS_THUMBNAILS_DIRECTORY",
            "thumbs",
            settings.nas_thumbs_directory_configured,
        ),
        ("MEDIA_NAS_PLAYBACK_DIRECTORY", "playback", settings.nas_play_directory_configured),
    ]

    directories: list[dict[str, Any]] = []

    for config_key, key, configured_value in directory_specs:
        configured_value = configured_value or getattr(BaseApplicationSettings, config_key, None) or None

        candidates = _storage_path_candidates(config_key)
        resolved_path = _storage_path(config_key)
        if not resolved_path and candidates:
            resolved_path = candidates[0]
        if not resolved_path:
            resolved_path = configured_value

        path_info = _prepare_local_import_path(resolved_path)
        path_info["configured"] = configured_value
        path_info["candidates"] = candidates

        normalized_configured = (
            os.path.abspath(configured_value)
            if configured_value
            and isinstance(configured_value, str)
            and "://" not in configured_value
            else configured_value
        )
        normalized_effective = (
            os.path.abspath(path_info["absolute"])
            if path_info.get("absolute")
            and "://" not in path_info["absolute"]
            else path_info.get("absolute")
        )
        if normalized_configured and normalized_effective:
            source = (
                "configured"
                if normalized_configured == normalized_effective
                else "fallback"
            )
        elif configured_value and path_info.get("raw"):
            source = "configured"
        elif path_info.get("raw"):
            source = "fallback"
        else:
            source = "unknown"
        path_info["source"] = source

        directories.append(
            {
                "key": key,
                "config_key": config_key,
                "info": path_info,
            }
        )

    lookup = {entry["config_key"]: entry for entry in directories}

    def _info_or_empty(config_key: str) -> dict[str, Any]:
        entry = lookup.get(config_key)
        if entry:
            return entry["info"]
        return _prepare_local_import_path(None)

    return {
        "import_dir": lookup.get("MEDIA_LOCAL_IMPORT_DIRECTORY", {}).get("info", {}).get("raw"),
        "originals_dir": lookup.get("MEDIA_NAS_ORIGINALS_DIRECTORY", {}).get("info", {}).get("raw"),
        "import_dir_info": _info_or_empty("MEDIA_LOCAL_IMPORT_DIRECTORY"),
        "originals_dir_info": _info_or_empty("MEDIA_NAS_ORIGINALS_DIRECTORY"),
        "directories": directories,
    }


@bp.get("/sync/local-import/status")
@login_or_jwt_required
def local_import_status():
    """ローカルインポートの設定と状態を取得"""
    config_info = _resolve_local_import_config()

    import_dir_info = config_info["import_dir_info"]
    originals_dir_info = config_info["originals_dir_info"]

    directory_labels = {
        "MEDIA_LOCAL_IMPORT_DIRECTORY": _("Import directory"),
        "MEDIA_NAS_ORIGINALS_DIRECTORY": _("Originals directory"),
        "MEDIA_NAS_THUMBNAILS_DIRECTORY": _("Thumbnails directory"),
        "MEDIA_NAS_PLAYBACK_DIRECTORY": _("Playback directory"),
    }

    directories_payload: list[dict[str, Any]] = []
    for entry in config_info.get("directories", []):
        info = entry.get("info", {})
        directories_payload.append(
            {
                "key": entry.get("key"),
                "config_key": entry.get("config_key"),
                "label": directory_labels.get(entry.get("config_key"), entry.get("config_key")),
                "path": info.get("raw"),
                "absolute": info.get("absolute"),
                "realpath": info.get("realpath"),
                "exists": bool(info.get("exists")),
                "configured": info.get("configured"),
                "source": info.get("source"),
            }
        )

    # 取り込み対象ファイル数の計算
    file_count = 0
    if import_dir_info["exists"]:
        try:
            from core.tasks.local_import import scan_import_directory
            files = scan_import_directory(import_dir_info["realpath"])
            file_count = len(files)
        except Exception as e:
            _local_import_log(
                "Failed to scan local import directory",
                level="warning",
                event="local_import.api.status",
                stage="scan_failed",
                error=str(e),
                import_dir=import_dir_info["realpath"],
            )

    _local_import_log(
        "Local import status requested",
        event="local_import.api.status",
        stage="status",
        import_dir=config_info["import_dir"],
        import_dir_exists=import_dir_info["exists"],
        originals_dir=config_info["originals_dir"],
        originals_dir_exists=originals_dir_info["exists"],
        pending_files=file_count,
        directory_status={
            str(entry.get("config_key")): entry.get("exists")
            for entry in directories_payload
        },
    )

    all_directories_ready = all(entry.get("exists") for entry in directories_payload)

    return jsonify({
        "config": {
            "import_dir": config_info["import_dir"],
            "originals_dir": config_info["originals_dir"],
            "import_dir_absolute": import_dir_info["absolute"],
            "import_dir_realpath": import_dir_info["realpath"],
            "import_dir_exists": import_dir_info["exists"],
            "originals_dir_absolute": originals_dir_info["absolute"],
            "originals_dir_realpath": originals_dir_info["realpath"],
            "originals_dir_exists": originals_dir_info["exists"],
        },
        "status": {
            "pending_files": file_count,
            "ready": all_directories_ready,
        },
        "directories": directories_payload,
        "defaults": {
            "duplicateRegeneration": "regenerate",
        },
        "server_time": datetime.now(timezone.utc).isoformat(),
    })


@bp.post("/sync/local-import/directories")
@login_or_jwt_required
def ensure_local_import_directories():
    """Ensure that local import directories exist (admin only)."""

    user = get_current_user()
    if not user or not getattr(user, "can", None) or not user.can("system:manage"):
        _local_import_log(
            "Local import directory ensure rejected: insufficient permissions",
            level="warning",
            event="local_import.api.directories",
            stage="denied",
        )
        return (
            jsonify({"error": _("You do not have permission to manage local import directories.")}),
            403,
        )

    _local_import_log(
        "Local import directory ensure requested",
        event="local_import.api.directories",
        stage="start",
    )

    initial_config = _resolve_local_import_config()

    created = []
    errors = {}

    for key in ("import_dir", "originals_dir"):
        raw_path = initial_config.get(key)
        path_info = initial_config.get(f"{key}_info") or {}
        if not raw_path:
            continue

        if path_info.get("exists"):
            continue

        target_path = path_info.get("realpath") or os.path.abspath(raw_path)
        try:
            os.makedirs(target_path, exist_ok=True)
            created.append(key)
        except Exception as exc:  # pragma: no cover - defensive logging
            _local_import_log(
                "Failed to create local import directory",
                level="error",
                event="local_import.api.directories",
                stage="create_failed",
                target_path=target_path,
                error=str(exc),
            )
            errors[key] = str(exc)

    updated_config = _resolve_local_import_config()

    payload = {
        "success": len(errors) == 0,
        "created": created,
        "errors": errors,
        "config": {
            "import_dir": updated_config["import_dir"],
            "originals_dir": updated_config["originals_dir"],
            "import_dir_absolute": updated_config["import_dir_info"]["absolute"],
            "import_dir_realpath": updated_config["import_dir_info"]["realpath"],
            "import_dir_exists": updated_config["import_dir_info"]["exists"],
            "originals_dir_absolute": updated_config["originals_dir_info"]["absolute"],
            "originals_dir_realpath": updated_config["originals_dir_info"]["realpath"],
            "originals_dir_exists": updated_config["originals_dir_info"]["exists"],
        },
        "message": _("Directories created successfully.") if created else _("Directories already exist."),
        "server_time": datetime.now(timezone.utc).isoformat(),
    }

    status_code = 200 if not errors else 500
    if errors and not created:
        payload["message"] = _("Failed to create one or more directories.")

    _local_import_log(
        "Local import directory ensure completed",
        event="local_import.api.directories",
        stage="completed",
        created=created,
        errors=errors,
        status_code=status_code,
    )

    return jsonify(payload), status_code


@bp.get("/sync/local-import/task/<task_id>")
@login_or_jwt_required
def get_local_import_task_result(task_id):
    """ローカルインポートタスクの結果を取得"""

    user = get_current_user()
    if not user or not getattr(user, "can", None) or not user.can("system:manage"):
        _local_import_log(
            "Local import task result rejected: insufficient permissions",
            level="warning",
            event="local_import.api.task_status",
            stage="denied",
            task_id=task_id,
        )
        return (
            jsonify({"error": _("You do not have permission to view local import progress.")}),
            403,
        )

    from cli.src.celery.celery_app import celery

    _local_import_log(
        "Local import task result requested",
        event="local_import.api.task_status",
        stage="start",
        task_id=task_id,
    )

    try:
        # タスクの結果を取得
        result = celery.AsyncResult(task_id)

        if result.state == 'PENDING':
            response = {
                "state": result.state,
                "status": "タスクが実行待ちです",
                "progress": 0
            }
        elif result.state == 'PROGRESS':
            response = {
                "state": result.state,
                "status": result.info.get('status', ''),
                "progress": result.info.get('progress', 0),
                "current": result.info.get('current', 0),
                "total": result.info.get('total', 0),
                "message": result.info.get('message', '')
            }
        elif result.state == 'SUCCESS':
            response = {
                "state": result.state,
                "status": "完了",
                "progress": 100,
                "result": result.result
            }
        else:  # FAILURE
            response = {
                "state": result.state,
                "status": "エラー",
                "progress": 0,
                "error": str(result.info)
            }

        response["server_time"] = datetime.now(timezone.utc).isoformat()

        _local_import_log(
            "Local import task result returned",
            event="local_import.api.task_status",
            stage="completed",
            task_id=task_id,
            state=response.get("state"),
            progress=response.get("progress"),
            status=response.get("status"),
            has_error=response.get("error") is not None,
        )
        return jsonify(response)

    except Exception as e:
        _local_import_log(
            "Failed to get local import task result",
            level="error",
            event="local_import.api.task_status",
            stage="error",
            task_id=task_id,
            error=str(e),
        )
        return jsonify({
            "state": "ERROR",
            "status": "タスク結果の取得に失敗しました",
            "error": str(e),
            "server_time": datetime.now(timezone.utc).isoformat()
        }), 500



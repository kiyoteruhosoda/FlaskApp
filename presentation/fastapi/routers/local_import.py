"""ローカルインポート API（FastAPI）。

Flask-Smorest 版 ``presentation/web/api/routes_local_import.py`` を移植。
"""
from __future__ import annotations

import logging
import os
import random
import string
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.kernel.database.session import get_db
from shared.kernel.settings.settings import settings
from presentation.fastapi.dependencies.auth import get_current_principal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sync", tags=["local-import"])


def _local_import_log(msg: str, level: str = "info", **kwargs) -> None:
    getattr(logger, level)(msg, extra=kwargs)


def _storage_service():
    from presentation.web.api.routes import _storage_service as _svc
    return _svc()


def _storage_path(config_key: str):
    from presentation.web.api.routes import _storage_path as _sp
    return _sp(config_key)


def _storage_path_candidates(config_key: str):
    from presentation.web.api.routes import _storage_path_candidates as _spc
    return _spc(config_key)


def _prepare_local_import_path(path_value) -> dict:
    if not path_value:
        return {"raw": None, "absolute": None, "realpath": None, "exists": False}
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
    return {"raw": path_value, "absolute": absolute, "realpath": realpath, "exists": exists}


def _resolve_local_import_config() -> dict:
    from presentation.web.bootstrap.config import BaseApplicationSettings

    directory_specs = [
        ("MEDIA_LOCAL_IMPORT_DIRECTORY", "import", settings.local_import_directory_configured),
        ("MEDIA_ORIGINALS_DIRECTORY", "originals", settings.media_originals_directory),
        ("MEDIA_THUMBNAILS_DIRECTORY", "thumbs", settings.media_thumbs_directory),
        ("MEDIA_PLAYBACK_DIRECTORY", "playback", settings.media_play_directory),
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
            if configured_value and isinstance(configured_value, str) and "://" not in configured_value
            else configured_value
        )
        normalized_effective = (
            os.path.abspath(path_info["absolute"])
            if path_info.get("absolute") and "://" not in path_info["absolute"]
            else path_info.get("absolute")
        )
        if normalized_configured and normalized_effective:
            source = "configured" if normalized_configured == normalized_effective else "fallback"
        elif configured_value and path_info.get("raw"):
            source = "configured"
        elif path_info.get("raw"):
            source = "fallback"
        else:
            source = "unknown"
        path_info["source"] = source
        directories.append({"key": key, "config_key": config_key, "info": path_info})

    lookup = {entry["config_key"]: entry for entry in directories}

    def _info_or_empty(config_key: str) -> dict:
        entry = lookup.get(config_key)
        return entry["info"] if entry else _prepare_local_import_path(None)

    return {
        "import_dir": lookup.get("MEDIA_LOCAL_IMPORT_DIRECTORY", {}).get("info", {}).get("raw"),
        "originals_dir": lookup.get("MEDIA_ORIGINALS_DIRECTORY", {}).get("info", {}).get("raw"),
        "import_dir_info": _info_or_empty("MEDIA_LOCAL_IMPORT_DIRECTORY"),
        "originals_dir_info": _info_or_empty("MEDIA_ORIGINALS_DIRECTORY"),
        "directories": directories,
    }


@router.post("/local-import")
async def trigger_local_import(
    body: dict = {},
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """ローカルファイル取り込みを手動実行する（system:manage 権限必要）。"""
    from bounded_contexts.picker_import.infrastructure.picker_session import PickerSession

    if not principal.can("system:manage"):
        _local_import_log("Local import trigger rejected", level="warning", stage="denied")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "You do not have permission to start a local import."},
        )

    duplicate_regeneration = body.get("duplicateRegeneration") or "regenerate"
    if isinstance(duplicate_regeneration, str):
        duplicate_regeneration = duplicate_regeneration.lower()
    if duplicate_regeneration not in {"regenerate", "skip"}:
        duplicate_regeneration = "regenerate"

    _local_import_log("Local import trigger requested", stage="start", duplicate_regeneration=duplicate_regeneration)

    try:
        from cli.src.celery.tasks import local_import_task_celery

        now = datetime.now(timezone.utc)
        random_suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
        session_id = f"local_import_{now.strftime('%Y%m%d_%H%M%S')}_{now.microsecond}_{random_suffix}"

        picker_session = PickerSession(
            account_id=None,
            session_id=session_id,
            status="processing",
            selected_count=0,
            created_at=now,
            updated_at=now,
            last_progress_at=now,
            trigger="user",
            triggered_by_user_id=int(principal.user_id),
        )
        stats = picker_session.stats() if hasattr(picker_session, "stats") else {}
        if not isinstance(stats, dict):
            stats = {}
        options = stats.get("options") or {}
        options["duplicateRegeneration"] = duplicate_regeneration
        stats["options"] = options
        picker_session.set_stats(stats)
        db.add(picker_session)
        db.commit()

        task = local_import_task_celery.delay(session_id)

        _local_import_log(
            "Local import task dispatched",
            stage="dispatched",
            session_id=session_id,
            celery_task_id=task.id,
        )

        return {
            "success": True,
            "task_id": task.id,
            "session_id": session_id,
            "message": "ローカルインポートタスクを開始しました",
            "server_time": now.isoformat(),
            "duplicateRegeneration": duplicate_regeneration,
        }
    except Exception as exc:
        _local_import_log("Failed to start local import task", level="error", stage="error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"success": False, "error": str(exc), "server_time": datetime.now(timezone.utc).isoformat()},
        )


@router.post("/local-import/{session_id:path}/stop")
async def stop_local_import(
    session_id: str,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """ローカルインポートを停止（キャンセル）する。"""
    from bounded_contexts.picker_import.infrastructure.picker_session import PickerSession
    from bounded_contexts.photonest.infrastructure.photo_models import PickerSelection

    if not principal.can("system:manage"):
        _local_import_log("Local import stop rejected", level="warning", stage="denied")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "You do not have permission to stop a local import."},
        )

    picker_session = (
        db.query(PickerSession).filter_by(session_id=session_id, account_id=None).first()
    )
    if not picker_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Local import session not found."},
        )

    cancelable_statuses = {"expanding", "processing", "importing", "enqueued"}
    if picker_session.status == "canceled":
        return {"success": True, "message": "Local import session is already canceled.", "session_id": session_id}
    if picker_session.status not in cancelable_statuses:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "Local import session is not currently running."},
        )

    now = datetime.now(timezone.utc)
    stats = picker_session.stats() if hasattr(picker_session, "stats") else {}
    if not isinstance(stats, dict):
        stats = {}
    celery_task_id = stats.get("celery_task_id")

    pending_statuses = ("pending", "enqueued")
    skipped_items = (
        db.query(PickerSelection)
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
    db.flush()

    counts_query = (
        db.query(PickerSelection.status, db.func.count(PickerSelection.id))
        .filter(PickerSelection.session_id == picker_session.id)
        .group_by(PickerSelection.status)
        .all()
    )
    counts_map = {row[0]: row[1] for row in counts_query}
    pending_remaining = sum(counts_map.get(s, 0) for s in ("pending", "enqueued", "running"))
    imported_count = counts_map.get("imported", 0)
    dup_count = counts_map.get("dup", 0)
    skipped_total = counts_map.get("skipped", 0) + dup_count
    failed_count = counts_map.get("failed", 0)

    picker_session.selected_count = imported_count
    stats.update({
        "stage": "canceling",
        "cancel_requested": True,
        "canceled_at": now.isoformat().replace("+00:00", "Z"),
        "total": imported_count + skipped_total + failed_count,
        "success": imported_count,
        "skipped": skipped_total,
        "failed": failed_count,
        "pending": pending_remaining,
    })
    picker_session.set_stats(stats)
    db.commit()

    revoke_error = None
    if celery_task_id:
        try:
            from cli.src.celery.celery_app import celery
            celery.control.revoke(celery_task_id, terminate=False)
        except Exception as exc:
            revoke_error = str(exc)

    payload: dict = {
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
        "message": "Local import session was canceled.",
    }
    if revoke_error:
        payload["revoke_error"] = revoke_error
    return payload


@router.get("/local-import/status")
async def local_import_status(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """ローカルインポートの設定と状態を取得する。"""
    config_info = _resolve_local_import_config()
    import_dir_info = config_info["import_dir_info"]
    originals_dir_info = config_info["originals_dir_info"]

    directory_labels = {
        "MEDIA_LOCAL_IMPORT_DIRECTORY": "Import directory",
        "MEDIA_ORIGINALS_DIRECTORY": "Originals directory",
        "MEDIA_THUMBNAILS_DIRECTORY": "Thumbnails directory",
        "MEDIA_PLAYBACK_DIRECTORY": "Playback directory",
    }

    directories_payload: list[dict] = []
    for entry in config_info.get("directories", []):
        info = entry.get("info", {})
        directories_payload.append({
            "key": entry.get("key"),
            "config_key": entry.get("config_key"),
            "label": directory_labels.get(entry.get("config_key"), entry.get("config_key")),
            "path": info.get("raw"),
            "absolute": info.get("absolute"),
            "realpath": info.get("realpath"),
            "exists": bool(info.get("exists")),
            "configured": info.get("configured"),
            "source": info.get("source"),
        })

    file_count = 0
    if import_dir_info["exists"]:
        try:
            from bounded_contexts.photonest.tasks.local_import import scan_import_directory
            files = scan_import_directory(import_dir_info["realpath"])
            file_count = len(files)
        except Exception as exc:
            _local_import_log("Failed to scan local import directory", level="warning", error=str(exc))

    all_directories_ready = all(entry.get("exists") for entry in directories_payload)

    return {
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
        "status": {"pending_files": file_count, "ready": all_directories_ready},
        "directories": directories_payload,
        "defaults": {"duplicateRegeneration": "regenerate"},
        "server_time": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/local-import/upload")
async def upload_local_import_files(
    files: list[UploadFile] = File(...),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """取り込みディレクトリへファイルを手動アップロードする。"""
    from bounded_contexts.photonest.domain.local_import.policies import SUPPORTED_EXTENSIONS

    if not principal.can("admin:photo-settings"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "You do not have permission to upload import files."},
        )

    config_info = _resolve_local_import_config()
    import_dir_info = config_info["import_dir_info"]
    if not import_dir_info.get("exists"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "Import directory does not exist."},
        )

    if not files:
        raise HTTPException(status_code=400, detail={"error": "No files were provided."})

    import_dir = import_dir_info["realpath"]
    saved: list[dict] = []
    skipped: list[dict] = []

    for upload_file in files:
        original_name = os.path.basename(upload_file.filename or "").strip()
        if not original_name or original_name.startswith("."):
            skipped.append({"filename": upload_file.filename or "", "reason": "invalid_filename"})
            continue

        extension = os.path.splitext(original_name)[1].lower()
        if extension not in SUPPORTED_EXTENSIONS:
            skipped.append({"filename": original_name, "reason": "unsupported_extension"})
            continue

        target_name = original_name
        stem, suffix = os.path.splitext(original_name)
        counter = 1
        while os.path.exists(os.path.join(import_dir, target_name)):
            target_name = f"{stem}_{counter}{suffix}"
            counter += 1

        target_path = os.path.join(import_dir, target_name)
        try:
            content = await upload_file.read()
            with open(target_path, "wb") as f:
                f.write(content)
        except Exception as exc:
            _local_import_log("Failed to save uploaded import file", level="error", filename=original_name, error=str(exc))
            skipped.append({"filename": original_name, "reason": "save_failed"})
            continue

        saved.append({"filename": target_name, "size": os.path.getsize(target_path)})

    return {
        "success": len(saved) > 0,
        "saved": saved,
        "skipped": skipped,
        "server_time": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/local-import/directories")
async def ensure_local_import_directories(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """ローカルインポートディレクトリを作成する（system:manage 権限必要）。"""
    if not principal.can("system:manage"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "You do not have permission to manage local import directories."},
        )

    initial_config = _resolve_local_import_config()
    created = []
    errors: dict[str, str] = {}

    for key in ("import_dir", "originals_dir"):
        raw_path = initial_config.get(key)
        path_info = initial_config.get(f"{key}_info") or {}
        if not raw_path or path_info.get("exists"):
            continue
        target_path = path_info.get("realpath") or os.path.abspath(raw_path)
        try:
            os.makedirs(target_path, exist_ok=True)
            created.append(key)
        except Exception as exc:
            errors[key] = str(exc)

    updated_config = _resolve_local_import_config()
    return {
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
        "message": "Directories created successfully." if created else "Directories already exist.",
        "server_time": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/local-import/task/{task_id}")
async def get_local_import_task_result(
    task_id: str,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
):
    """ローカルインポートタスクの結果を取得する。"""
    if not principal.can("system:manage"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "You do not have permission to view local import progress."},
        )

    try:
        from cli.src.celery.celery_app import celery
        result = celery.AsyncResult(task_id)

        if result.state == "PENDING":
            response: dict = {"state": result.state, "status": "タスクが実行待ちです", "progress": 0}
        elif result.state == "PROGRESS":
            response = {
                "state": result.state,
                "status": result.info.get("status", ""),
                "progress": result.info.get("progress", 0),
                "current": result.info.get("current", 0),
                "total": result.info.get("total", 0),
                "message": result.info.get("message", ""),
            }
        elif result.state == "SUCCESS":
            response = {"state": result.state, "status": "完了", "progress": 100, "result": result.result}
        else:
            response = {"state": result.state, "status": "エラー", "progress": 0, "error": str(result.info)}

        response["server_time"] = datetime.now(timezone.utc).isoformat()
        return response
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"state": "ERROR", "status": "タスク結果の取得に失敗しました", "error": str(exc)},
        )

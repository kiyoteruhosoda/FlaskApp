"""管理 JSON API — Photo Exports (`/api/admin/photo-exports`)。

オリジナル画像・動画を ZIP 形式でダウンロードする。
対象は ``imported_at`` の日付範囲と最大件数でフィルタできる。
"""
from __future__ import annotations

import io
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

from flask import jsonify, request, Response, stream_with_context

from ..bootstrap.extensions import db
from bounded_contexts.photonest.infrastructure.photo_models import Media
from shared.kernel.settings.settings import settings
from . import bp
from .routes import login_or_jwt_required, get_current_user


def _require_system_manage():
    user = get_current_user()
    if user is None or not user.can("system:manage"):
        return jsonify({"error": "forbidden", "message": "system:manage permission required"}), 403
    return None


@bp.get("/admin/photo-exports/preview")
@login_or_jwt_required
def api_admin_photo_exports_preview():
    """エクスポート対象のメディア件数と合計サイズをプレビューする。"""
    err = _require_system_manage()
    if err:
        return err

    date_from, date_to, limit, err_resp = _parse_filter_params()
    if err_resp:
        return err_resp

    query = _build_media_query(date_from, date_to)
    total = query.count()
    capped = query.limit(limit).all()

    total_size = sum(m.file_size or 0 for m in capped)
    return jsonify({
        "matchedCount": total,
        "exportCount": len(capped),
        "totalBytes": total_size,
        "limit": limit,
    })


@bp.get("/admin/photo-exports/download")
@login_or_jwt_required
def api_admin_photo_exports_download():
    """対象メディアを ZIP にまとめてストリーミングダウンロードする。"""
    err = _require_system_manage()
    if err:
        return err

    date_from, date_to, limit, err_resp = _parse_filter_params()
    if err_resp:
        return err_resp

    query = _build_media_query(date_from, date_to)
    media_list = query.limit(limit).all()

    originals_dir = settings.storage_originals_directory

    def generate():
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
            seen_names: set[str] = set()
            for media in media_list:
                if not media.local_rel_path:
                    continue
                abs_path = originals_dir / media.local_rel_path
                if not abs_path.exists():
                    continue
                # アーカイブ内のファイル名を重複回避
                arc_name = _unique_arcname(abs_path.name, seen_names)
                seen_names.add(arc_name)
                zf.write(str(abs_path), arc_name)
        buffer.seek(0)
        yield buffer.read()

    filename = "photo_exports_{}.zip".format(
        datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    )
    return Response(
        stream_with_context(generate()),
        mimetype="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_filter_params():
    """クエリパラメータをパースして (date_from, date_to, limit, error_response) を返す。"""
    raw_from = request.args.get("dateFrom", "").strip()
    raw_to = request.args.get("dateTo", "").strip()
    raw_limit = request.args.get("limit", "500").strip()

    date_from: datetime | None = None
    date_to: datetime | None = None

    if raw_from:
        try:
            date_from = datetime.fromisoformat(raw_from).replace(tzinfo=timezone.utc)
        except ValueError:
            return None, None, None, (jsonify({"error": "invalid_date_from"}), 400)

    if raw_to:
        try:
            date_to = datetime.fromisoformat(raw_to).replace(tzinfo=timezone.utc)
            # 終了日は当日の23:59:59まで含める
            if date_to.hour == 0 and date_to.minute == 0 and date_to.second == 0:
                date_to = date_to + timedelta(days=1) - timedelta(seconds=1)
        except ValueError:
            return None, None, None, (jsonify({"error": "invalid_date_to"}), 400)

    try:
        limit = int(raw_limit)
        if limit < 1 or limit > 5000:
            raise ValueError
    except ValueError:
        return None, None, None, (jsonify({"error": "invalid_limit", "message": "limit must be 1–5000"}), 400)

    return date_from, date_to, limit, None


def _build_media_query(date_from: datetime | None, date_to: datetime | None):
    """フィルタを適用したメディアクエリを返す（削除済みを除く）。"""
    from sqlalchemy import and_, or_

    not_deleted = or_(Media.is_deleted.is_(False), Media.is_deleted.is_(None))
    conditions = [not_deleted]
    if date_from:
        conditions.append(Media.imported_at >= date_from)
    if date_to:
        conditions.append(Media.imported_at <= date_to)

    return (
        Media.query
        .filter(and_(*conditions))
        .order_by(Media.imported_at.asc(), Media.id.asc())
    )


def _unique_arcname(name: str, seen: set[str]) -> str:
    """アーカイブ内の重複ファイル名を連番で回避する。"""
    if name not in seen:
        return name
    stem = Path(name).stem
    suffix = Path(name).suffix
    i = 1
    while True:
        candidate = f"{stem}_{i}{suffix}"
        if candidate not in seen:
            return candidate
        i += 1

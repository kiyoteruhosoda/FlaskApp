"""Routes for the photo view section.

These endpoints currently render simple placeholder templates that will be
expanded with full functionality later.  Having them in place allows the UI
navigation to be wired up and provides a starting point for further
implementation work.
"""

import os

from flask import abort, redirect, render_template, request, url_for
from flask_login import current_user

from core.models.authz import require_perms
from core.models.google_account import GoogleAccount
from core.settings import settings as app_settings

from . import bp
from webapp.api.picker_session_service import PickerSessionService


def _build_local_import_info():
    """Return resolved paths for local import directories."""

    def _resolve(path_value):
        if not path_value:
            return {
                "raw": None,
                "absolute": None,
                "realpath": None,
                "display": None,
                "exists": False,
            }

        absolute = os.path.abspath(path_value)
        realpath = os.path.realpath(absolute)
        exists = os.path.isdir(realpath)
        display = realpath if realpath else absolute
        if not display:
            display = path_value
        return {
            "raw": path_value,
            "absolute": absolute,
            "realpath": realpath,
            "display": display,
            "exists": exists,
        }

    import_info = _resolve(app_settings.local_import_directory_configured)
    originals_info = _resolve(app_settings.media_originals_directory)

    return {
        "import": import_info,
        "originals": originals_info,
    }


@bp.route("/", strict_slashes=False)
@require_perms("media:view")
def home():
    """Photo view home page."""
    session_id = request.args.get("session_id")
    if session_id:
        return redirect(url_for("photo_view.session_detail", session_id=session_id))

    google_accounts = []
    if current_user.is_authenticated and getattr(current_user, "id", None):
        google_accounts = (
            GoogleAccount.query.filter_by(user_id=current_user.id, status="active")
            .order_by(GoogleAccount.email.asc())
            .all()
        )

    return render_template(
        "photo-view/home.html",
        google_accounts=google_accounts,
        local_import_info=_build_local_import_info(),
        is_admin=(
            current_user.can("admin:photo-settings")
            if current_user.is_authenticated
            else False
        ),
        can_view_sessions=(
            True
            if app_settings.login_disabled
            else (
                current_user.can("media:session")
                if current_user.is_authenticated
                else False
            )
        ),
    )


@bp.route("/session/<path:session_id>", strict_slashes=False)
@require_perms("media:view", "media:session")
def session_detail(session_id: str):
    """Render the detail page for a single picker session."""

    return render_template(
        "photo-view/session_detail.html", picker_session_id=session_id
    )


@bp.route("/session/<path:session_id>/selection/<int:selection_id>/error")
@require_perms("media:view")
def selection_error_detail(session_id: str, selection_id: int):
    """Render a detail page showing why a selection failed."""

    ps = PickerSessionService.resolve_session_identifier(session_id)
    if not ps:
        abort(404)

    payload = PickerSessionService.selection_error_payload(ps, selection_id)
    if not payload:
        abort(404)

    session_detail_url = url_for(
        "photo_view.session_detail", session_id=payload["session"]["sessionId"]
    )

    return render_template(
        "photo-view/selection_error_detail.html",
        payload=payload,
        session_detail_url=session_detail_url,
    )


@bp.route("/media")
@require_perms("media:view")
def media_list():
    """List of media items with infinite scroll (placeholder)."""
    return render_template("photo-view/media_list.html")


@bp.route("/media/<int:media_id>")
@require_perms("media:view")
def media_detail(media_id: int):
    """Detail view for a single media item."""
    return render_template("photo-view/media_detail.html", media_id=media_id)


@bp.route("/albums")
@require_perms("media:view", "album:view")
def albums():
    """List of albums."""
    return render_template("photo-view/albums.html", editor_view=False)


@bp.route("/albums/<int:album_id>")
@require_perms("media:view", "album:view")
def album_detail(album_id: int):
    """Detail view for a single album."""
    return render_template("photo-view/album_detail.html", album_id=album_id)


@bp.route("/albums/create")
@require_perms("media:view", "album:view")
def album_create():
    """Standalone page for creating a new album."""
    return render_template(
        "photo-view/albums.html",
        editor_view=True,
        editor_album_id=None,
        editor_success_url=url_for("photo_view.albums"),
        editor_cancel_url=url_for("photo_view.albums"),
    )


@bp.route("/albums/<int:album_id>/edit")
@require_perms("media:view", "album:view")
def album_edit(album_id: int):
    """Standalone page for editing an existing album."""

    return render_template(
        "photo-view/albums.html",
        editor_view=True,
        editor_album_id=album_id,
        editor_success_url=url_for("photo_view.album_detail", album_id=album_id),
        editor_cancel_url=url_for("photo_view.album_detail", album_id=album_id),
    )


@bp.route("/albums/<int:album_id>/slideshow")
@require_perms("media:view", "album:view")
def album_slideshow(album_id: int):
    """Dedicated slideshow view for an album."""

    start_index = request.args.get("start", type=int)
    autoplay = request.args.get("autoplay", default="1")
    autoplay_enabled = str(autoplay).lower() not in {"0", "false", "no"}

    return render_template(
        "photo-view/album_slideshow.html",
        album_id=album_id,
        start_index=start_index if isinstance(start_index, int) else None,
        autoplay_enabled=autoplay_enabled,
    )


@bp.route("/tags")
@require_perms("media:view")
def tags():
    """List of tags."""
    return render_template("photo-view/tags.html")


@bp.route("/settings")
@require_perms("admin:photo-settings")
@require_perms("media:view")
def settings():
    """Photo view settings page."""
    return render_template(
        "photo-view/settings.html",
        local_import_info=_build_local_import_info(),
        is_admin=(
            current_user.can("admin:photo-settings")
            if current_user.is_authenticated
            else False
        ),
    )


# --- Admin routes ---------------------------------------------------------


@bp.route("/admin/exports")
@require_perms("system:manage")
def admin_exports():
    """Placeholder admin exports listing page."""

    return render_template("photo-view/admin/exports.html")


@bp.route("/admin/exports/<int:export_id>")
@require_perms("system:manage")
def admin_export_detail(export_id: int):
    """Placeholder admin export detail page."""

    return render_template(
        "photo-view/admin/export_detail.html", export_id=export_id
    )

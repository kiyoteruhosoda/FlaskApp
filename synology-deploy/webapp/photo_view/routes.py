"""Routes for the photo view section.

These endpoints currently render simple placeholder templates that will be
expanded with full functionality later.  Having them in place allows the UI
navigation to be wired up and provides a starting point for further
implementation work.
"""

from flask import render_template, session, request

from core.models.authz import require_roles, require_perms

from . import bp


@bp.route("/")
@require_perms("media:view")
def home():
    """Photo view home page."""
    # クエリパラメータでsession_idが指定されている場合は詳細ページを表示
    session_id = request.args.get('session_id')
    if session_id:
        return render_template("photo_view/session_detail.html", picker_session_id=session_id)
    
    # session_idがない場合は、すべてのセッション一覧を表示
    return render_template("photo_view/home.html")


@bp.route("/media")
@require_perms("media:view")
def media_list():
    """List of media items with infinite scroll (placeholder)."""
    return render_template("photo_view/media_list.html")


@bp.route("/media/<int:media_id>")
@require_perms("media:view")
def media_detail(media_id: int):
    """Detail view for a single media item."""
    return render_template("photo_view/media_detail.html", media_id=media_id)


@bp.route("/albums")
@require_perms("media:view", "album:view")
def albums():
    """List of albums."""
    return render_template("photo_view/albums.html")


@bp.route("/albums/<int:album_id>")
@require_perms("media:view", "album:view")
def album_detail(album_id: int):
    """Detail view for a single album."""
    return render_template("photo_view/album_detail.html", album_id=album_id)


@bp.route("/tags")
@require_perms("media:view")
def tags():
    """List of tags."""
    return render_template("photo_view/tags.html")


@bp.route("/settings")
@require_perms("media:view")
def settings():
    """Photo view settings page."""
    return render_template("photo_view/settings.html")


# --- Admin routes ---------------------------------------------------------


@bp.route("/admin/settings")
@require_roles("admin")
def admin_settings():
    """Placeholder admin settings page.

    The actual UI will be implemented in later tasks.  Having this route in
    place allows navigation and access control wiring to be verified.
    """

    return render_template("photo_view/admin/settings.html")


@bp.route("/admin/exports")
@require_roles("admin")
def admin_exports():
    """Placeholder admin exports listing page."""

    return render_template("photo_view/admin/exports.html")


@bp.route("/admin/exports/<int:export_id>")
@require_roles("admin")
def admin_export_detail(export_id: int):
    """Placeholder admin export detail page."""

    return render_template(
        "photo_view/admin/export_detail.html", export_id=export_id
    )

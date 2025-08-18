"""Routes for the photo view section.

These endpoints currently render simple placeholder templates that will be
expanded with full functionality later.  Having them in place allows the UI
navigation to be wired up and provides a starting point for further
implementation work.
"""

from flask import render_template

from . import bp


@bp.route("/")
def home():
    """Photo view home page."""
    return render_template("photo_view/home.html")


@bp.route("/media")
def media_list():
    """List of media items with infinite scroll (placeholder)."""
    return render_template("photo_view/media_list.html")


@bp.route("/media/<int:media_id>")
def media_detail(media_id: int):
    """Detail view for a single media item."""
    return render_template("photo_view/media_detail.html", media_id=media_id)


@bp.route("/albums")
def albums():
    """List of albums."""
    return render_template("photo_view/albums.html")


@bp.route("/albums/<int:album_id>")
def album_detail(album_id: int):
    """Detail view for a single album."""
    return render_template("photo_view/album_detail.html", album_id=album_id)


@bp.route("/tags")
def tags():
    """List of tags."""
    return render_template("photo_view/tags.html")


@bp.route("/settings")
def settings():
    """Photo view settings page."""
    return render_template("photo_view/settings.html")

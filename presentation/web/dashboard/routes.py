from flask import render_template
from flask_login import current_user

from core.models.authz import require_perms
from . import bp


@bp.route("/")
@require_perms("dashboard:view")
def dashboard():
    """Render the workspace dashboard with aggregated stats."""

    user_roles = list(getattr(current_user, "roles", []) or [])
    active_role = getattr(current_user, "active_role", None)
    if active_role is None and user_roles:
        active_role_name = getattr(user_roles[0], "name", None)
    else:
        active_role_name = getattr(active_role, "name", None)

    stats = {
        "wiki_pages": 0,
        "media_count": 0,
        "role_count": len(user_roles),
        "active_role": active_role_name,
        "display_name": getattr(current_user, "display_name", ""),
    }

    try:
        # Wikiページ数を取得
        from bounded_contexts.wiki.infrastructure.repositories import WikiPageRepository

        wiki_repo = WikiPageRepository()
        stats["wiki_pages"] = wiki_repo.count_published_pages()
    except Exception:
        stats["wiki_pages"] = 0

    try:
        # メディア数を取得（権限がある場合のみ）
        if current_user.can("media:view"):
            from core.models.photo_models import Media

            stats["media_count"] = Media.query.count()
        else:
            stats["media_count"] = 0
    except Exception:
        stats["media_count"] = 0

    return render_template("dashboard/index.html", stats=stats)

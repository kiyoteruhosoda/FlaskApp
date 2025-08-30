from flask import render_template
from flask_login import login_required, current_user
from flask_babel import gettext as _
from . import bp

@bp.route("/dashboard")
@login_required
def dashboard():
    # 統計情報を取得
    stats = {}
    
    try:
        # Wikiページ数を取得
        from infrastructure.wiki.repositories import WikiPageRepository
        wiki_repo = WikiPageRepository()
        stats['wiki_pages'] = wiki_repo.count_published_pages()
    except Exception:
        stats['wiki_pages'] = 0
    
    try:
        # メディア数を取得（権限がある場合のみ）
        if current_user.can('media:view'):
            from core.models.photo_models import Media
            stats['media_count'] = Media.query.count()
        else:
            stats['media_count'] = 0
    except Exception:
        stats['media_count'] = 0
    
    return render_template("feature_x/dashboard.html", stats=stats)

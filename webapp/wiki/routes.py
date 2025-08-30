"""
Wiki機能のWebルート
"""

from flask import render_template, request, redirect, url_for, flash, jsonify, abort
from flask_login import login_required, current_user
from core.models.authz import require_perms
from . import bp
from application.wiki.services import WikiPageService, WikiCategoryService


@bp.route("/")
@require_perms("wiki:read")
def index():
    """Wiki トップページ"""
    wiki_service = WikiPageService()
    recent_pages = wiki_service.get_recent_pages(limit=10)
    page_hierarchy = wiki_service.get_page_hierarchy()
    
    category_service = WikiCategoryService()
    categories = category_service.get_all_categories()
    
    return render_template("wiki/index.html", 
                         recent_pages=recent_pages,
                         page_hierarchy=page_hierarchy,
                         categories=categories)


@bp.route("/page/<slug>")
@require_perms("wiki:read")
def view_page(slug):
    """Wikiページ表示"""
    wiki_service = WikiPageService()
    page = wiki_service.get_page_by_slug(slug)
    
    if not page or not page.is_published:
        abort(404)
    
    # 子ページを取得
    children = wiki_service.get_page_hierarchy(page.id)
    
    return render_template("wiki/page.html", page=page, children=children)


@bp.route("/create", methods=["GET", "POST"])
@require_perms("wiki:write")
def create_page():
    """Wikiページ作成"""
    if request.method == "GET":
        category_service = WikiCategoryService()
        categories = category_service.get_all_categories()
        
        wiki_service = WikiPageService()
        pages = wiki_service.get_recent_pages(limit=50)  # 親ページ選択用
        
        return render_template("wiki/create.html", categories=categories, pages=pages)
    
    # POST処理
    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()
    slug = request.form.get("slug", "").strip()
    parent_id = request.form.get("parent_id")
    category_ids = request.form.getlist("category_ids")
    
    if not title or not content:
        flash("タイトルと内容は必須です", "error")
        return redirect(url_for("wiki.create_page"))
    
    try:
        parent_id = int(parent_id) if parent_id else None
        category_ids = [int(cid) for cid in category_ids if cid]
        
        wiki_service = WikiPageService()
        page = wiki_service.create_page(
            title=title,
            content=content,
            user_id=current_user.id,
            slug=slug or None,
            parent_id=parent_id,
            category_ids=category_ids
        )
        
        flash("ページを作成しました", "success")
        return redirect(url_for("wiki.view_page", slug=page.slug))
        
    except Exception as e:
        flash(f"ページ作成エラー: {str(e)}", "error")
        return redirect(url_for("wiki.create_page"))


@bp.route("/edit/<slug>", methods=["GET", "POST"])
@require_perms("wiki:write")
def edit_page(slug):
    """Wikiページ編集"""
    wiki_service = WikiPageService()
    page = wiki_service.get_page_by_slug(slug)
    
    if not page:
        abort(404)
    
    # 編集権限チェック（作成者のみ、または管理者権限）
    if page.created_by_id != current_user.id and not current_user.can('wiki:admin'):
        flash("このページを編集する権限がありません", "error")
        return redirect(url_for("wiki.view_page", slug=slug))
    
    if request.method == "GET":
        category_service = WikiCategoryService()
        categories = category_service.get_all_categories()
        
        return render_template("wiki/edit.html", page=page, categories=categories)
    
    # POST処理
    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()
    change_summary = request.form.get("change_summary", "").strip()
    category_ids = request.form.getlist("category_ids")
    
    if not title or not content:
        flash("タイトルと内容は必須です", "error")
        return redirect(url_for("wiki.edit_page", slug=slug))
    
    try:
        category_ids = [int(cid) for cid in category_ids if cid]
        
        updated_page = wiki_service.update_page(
            page_id=page.id,
            title=title,
            content=content,
            user_id=current_user.id,
            change_summary=change_summary,
            category_ids=category_ids
        )
        
        if updated_page:
            flash("ページを更新しました", "success")
            return redirect(url_for("wiki.view_page", slug=updated_page.slug))
        else:
            flash("ページの更新に失敗しました", "error")
            
    except Exception as e:
        flash(f"更新エラー: {str(e)}", "error")
    
    return redirect(url_for("wiki.edit_page", slug=slug))


@bp.route("/search")
@require_perms("wiki:read")
def search():
    """Wiki検索"""
    query = request.args.get("q", "").strip()
    
    if not query:
        return render_template("wiki/search.html", pages=[], query="")
    
    wiki_service = WikiPageService()
    pages = wiki_service.search_pages(query, limit=50)
    
    return render_template("wiki/search.html", pages=pages, query=query)


@bp.route("/category/<slug>")
@require_perms("wiki:read")
def view_category(slug):
    """カテゴリ別ページ一覧"""
    category_service = WikiCategoryService()
    category = category_service.get_category_by_slug(slug)
    
    if not category:
        abort(404)
    
    # カテゴリに属するページを取得
    from infrastructure.wiki.repositories import WikiPageRepository
    page_repo = WikiPageRepository()
    pages = page_repo.find_by_category_id(category.id)
    
    return render_template("wiki/category.html", category=category, pages=pages)


@bp.route("/history/<slug>")
@require_perms("wiki:read")
def page_history(slug):
    """ページ履歴表示"""
    wiki_service = WikiPageService()
    page = wiki_service.get_page_by_slug(slug)
    
    if not page:
        abort(404)
    
    revisions = wiki_service.get_page_revisions(page.id, limit=50)
    
    return render_template("wiki/history.html", page=page, revisions=revisions)


# API endpoints
@bp.route("/api/pages")
@require_perms("wiki:read")
def api_pages():
    """ページ一覧API"""
    wiki_service = WikiPageService()
    pages = wiki_service.get_recent_pages(limit=100)
    
    return jsonify({
        "pages": [page.to_dict() for page in pages]
    })


@bp.route("/api/search")
@require_perms("wiki:read")
def api_search():
    """検索API"""
    query = request.args.get("q", "").strip()
    limit = min(int(request.args.get("limit", 20)), 100)
    
    if not query:
        return jsonify({"pages": []})
    
    wiki_service = WikiPageService()
    pages = wiki_service.search_pages(query, limit=limit)
    
    return jsonify({
        "pages": [page.to_dict() for page in pages],
        "query": query
    })


# カテゴリ管理機能
@bp.route("/categories")
@require_perms("wiki:read")
def categories():
    """カテゴリ一覧"""
    category_service = WikiCategoryService()
    categories = category_service.get_all_categories()
    
    # 各カテゴリのページ数を取得
    from infrastructure.wiki.repositories import WikiPageRepository
    page_repo = WikiPageRepository()
    
    for category in categories:
        category.page_count = len(page_repo.find_by_category_id(category.id))
    
    return render_template("wiki/categories.html", categories=categories)


@bp.route("/categories/create", methods=["GET", "POST"])
@require_perms("wiki:admin")
def create_category():
    """カテゴリ作成"""
    if request.method == "GET":
        return render_template("wiki/create_category.html")
    
    # POST処理
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    slug = request.form.get("slug", "").strip()
    
    if not name:
        flash("カテゴリ名は必須です", "error")
        return redirect(url_for("wiki.create_category"))
    
    try:
        category_service = WikiCategoryService()
        category = category_service.create_category(
            name=name,
            description=description or None,
            slug=slug or None
        )
        
        flash("カテゴリを作成しました", "success")
        return redirect(url_for("wiki.view_category", slug=category.slug))
        
    except Exception as e:
        flash(f"カテゴリ作成エラー: {str(e)}", "error")
        return redirect(url_for("wiki.create_category"))


@bp.route("/admin")
@require_perms("wiki:admin")
def admin():
    """Wiki管理画面"""
    wiki_service = WikiPageService()
    category_service = WikiCategoryService()
    
    # 統計情報を取得
    from infrastructure.wiki.repositories import WikiPageRepository
    page_repo = WikiPageRepository()
    
    stats = {
        'total_pages': page_repo.count_published_pages(),
        'total_categories': len(category_service.get_all_categories()),
        'recent_pages': wiki_service.get_recent_pages(limit=5),
    }
    
    return render_template("wiki/admin.html", stats=stats)

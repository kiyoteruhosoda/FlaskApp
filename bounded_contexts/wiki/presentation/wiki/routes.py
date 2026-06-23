"""Wiki機能のWebルート - React SPA向けJSON API"""

from __future__ import annotations

from flask import (
    abort,
    current_app,
    jsonify,
    request,
)
from flask_login import current_user

from bounded_contexts.wiki.application.dto import (
    WikiCategoryCreateInput,
    WikiPageCreateInput,
    WikiPageDeleteInput,
    WikiPageUpdateInput,
)
from bounded_contexts.wiki.application.use_cases import (
    WikiAdminDashboardUseCase,
    WikiApiPagesUseCase,
    WikiApiSearchUseCase,
    WikiCategoryCreationUseCase,
    WikiCategoryDetailUseCase,
    WikiCategoryListUseCase,
    WikiIndexUseCase,
    WikiMarkdownPreviewUseCase,
    WikiPageCreationUseCase,
    WikiPageDetailUseCase,
    WikiPageEditPreparationUseCase,
    WikiPageFormPreparationUseCase,
    WikiPageHistoryUseCase,
    WikiPageDeletionUseCase,
    WikiPageUpdateUseCase,
)
from shared.infrastructure.models.authz import require_perms
from bounded_contexts.wiki.domain.exceptions import (
    WikiAccessDeniedError,
    WikiOperationError,
    WikiPageNotFoundError,
    WikiValidationError,
)

from . import bp


@bp.route("/api/index")
@require_perms("wiki:read")
def api_index():
    """Wikiトップページデータ"""
    view_model = WikiIndexUseCase().execute()
    return jsonify({
        "recent_pages": [p.to_dict() for p in view_model.recent_pages],
        "page_hierarchy": view_model.page_hierarchy,
        "categories": [c.to_dict() for c in view_model.categories],
    })


@bp.route("/api/pages", methods=["GET"])
@require_perms("wiki:read")
def api_pages():
    """ページ一覧API"""
    result = WikiApiPagesUseCase().execute(limit=100)
    return jsonify({"pages": [page.to_dict() for page in result.pages]})


@bp.route("/api/pages/<slug>", methods=["GET"])
@require_perms("wiki:read")
def api_page_detail(slug: str):
    """ページ詳細API"""
    try:
        view_model = WikiPageDetailUseCase().execute(slug)
    except WikiPageNotFoundError:
        return jsonify({"error": "Page not found"}), 404
    return jsonify({
        "page": view_model.page.to_dict(),
        "children": view_model.children,
        "categories": [c.to_dict() for c in view_model.categories],
        "page_hierarchy": view_model.page_hierarchy,
    })


@bp.route("/api/create-form", methods=["GET"])
@require_perms("wiki:write")
def api_create_form():
    """ページ作成フォームデータ"""
    form_data = WikiPageFormPreparationUseCase().execute()
    return jsonify({
        "categories": [c.to_dict() for c in form_data.categories],
        "pages": [p.to_dict() for p in form_data.pages],
    })


@bp.route("/api/pages", methods=["POST"])
@require_perms("wiki:write")
def api_create_page():
    """ページ作成API"""
    data = request.get_json(silent=True) or {}

    category_ids = data.get("category_ids", [])
    if isinstance(category_ids, str):
        category_ids = [category_ids] if category_ids else []

    payload = WikiPageCreateInput(
        title=data.get("title", ""),
        content=data.get("content", ""),
        slug=data.get("slug") or None,
        parent_id=data.get("parent_id") or None,
        category_ids=category_ids,
        author_id=current_user.id,
    )

    try:
        result = WikiPageCreationUseCase().execute(payload)
    except WikiValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except WikiOperationError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        current_app.logger.exception("Unexpected error creating wiki page")
        return jsonify({"error": str(exc)}), 500

    return jsonify({"page": result.page.to_dict()}), 201


@bp.route("/api/pages/<slug>/edit-form", methods=["GET"])
@require_perms("wiki:write")
def api_edit_form(slug: str):
    """ページ編集フォームデータ"""
    has_admin_rights = current_user.can("wiki:admin")
    try:
        view_model = WikiPageEditPreparationUseCase().execute(
            slug=slug,
            user_id=current_user.id,
            has_admin_rights=has_admin_rights,
        )
    except WikiPageNotFoundError:
        return jsonify({"error": "Page not found"}), 404
    except WikiAccessDeniedError as exc:
        return jsonify({"error": str(exc)}), 403
    return jsonify({
        "page": view_model.page.to_dict(),
        "categories": [c.to_dict() for c in view_model.categories],
    })


@bp.route("/api/pages/<slug>", methods=["PATCH"])
@require_perms("wiki:write")
def api_update_page(slug: str):
    """ページ更新API"""
    data = request.get_json(silent=True) or {}
    has_admin_rights = current_user.can("wiki:admin")

    category_ids = data.get("category_ids", [])
    if isinstance(category_ids, str):
        category_ids = [category_ids] if category_ids else []

    payload = WikiPageUpdateInput(
        slug=slug,
        title=data.get("title", ""),
        content=data.get("content", ""),
        change_summary=data.get("change_summary") or None,
        category_ids=category_ids,
        editor_id=current_user.id,
        has_admin_rights=has_admin_rights,
    )

    try:
        result = WikiPageUpdateUseCase().execute(payload)
    except WikiPageNotFoundError:
        return jsonify({"error": "Page not found"}), 404
    except WikiAccessDeniedError as exc:
        return jsonify({"error": str(exc)}), 403
    except WikiValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except WikiOperationError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        current_app.logger.exception("Unexpected error updating wiki page")
        return jsonify({"error": str(exc)}), 500

    return jsonify({"page": result.page.to_dict()})


@bp.route("/api/pages/<slug>", methods=["DELETE"])
@require_perms("wiki:write")
def api_delete_page(slug: str):
    """ページ削除API"""
    has_admin_rights = current_user.can("wiki:admin")
    payload = WikiPageDeleteInput(
        slug=slug,
        executor_id=current_user.id,
        has_admin_rights=has_admin_rights,
    )

    try:
        WikiPageDeletionUseCase().execute(payload)
    except WikiValidationError:
        return jsonify({"error": "Page identifier is required"}), 400
    except WikiPageNotFoundError:
        return jsonify({"error": "Page not found"}), 404
    except WikiAccessDeniedError:
        return jsonify({"error": "Permission denied"}), 403
    except WikiOperationError as exc:
        if str(exc) == "page_has_children":
            return jsonify({"error": "Cannot delete a page that has child pages"}), 400
        return jsonify({"error": "Failed to delete the page"}), 400
    except Exception:
        current_app.logger.exception("Unexpected error deleting wiki page", extra={"slug": slug})
        return jsonify({"error": "Failed to delete the page"}), 500

    return jsonify({"deleted": True, "slug": slug})


@bp.route("/api/pages/<slug>/history", methods=["GET"])
@require_perms("wiki:read")
def api_page_history(slug: str):
    """ページ履歴API"""
    try:
        view_model = WikiPageHistoryUseCase().execute(slug, limit=50)
    except WikiPageNotFoundError:
        return jsonify({"error": "Page not found"}), 404
    return jsonify({
        "page": view_model.page.to_dict(),
        "revisions": [r.to_dict() for r in view_model.revisions],
    })


@bp.route("/api/search", methods=["GET"])
@require_perms("wiki:read")
def api_search():
    """検索API"""
    limit = min(int(request.args.get("limit", 20)), 100)
    result = WikiApiSearchUseCase().execute(request.args.get("q", ""), limit=limit)
    return jsonify({
        "pages": [page.to_dict() for page in result.pages],
        "query": result.query,
    })


@bp.route("/api/preview", methods=["POST"])
@require_perms("wiki:read")
def api_preview():
    """Markdownプレビュー用API"""
    payload = request.get_json(silent=True) or {}
    content = payload.get("content", "")
    result = WikiMarkdownPreviewUseCase().execute(content)
    return jsonify({"html": result.html})


@bp.route("/api/categories", methods=["GET"])
@require_perms("wiki:read")
def api_categories():
    """カテゴリ一覧API"""
    view_model = WikiCategoryListUseCase().execute()
    return jsonify({
        "categories": [
            {**item.category.to_dict(), "page_count": item.page_count}
            for item in view_model.categories
        ]
    })


@bp.route("/api/categories", methods=["POST"])
@require_perms("wiki:admin")
def api_create_category():
    """カテゴリ作成API"""
    data = request.get_json(silent=True) or {}
    payload = WikiCategoryCreateInput(
        name=data.get("name", ""),
        description=data.get("description") or None,
        slug=data.get("slug") or None,
    )

    try:
        result = WikiCategoryCreationUseCase().execute(payload)
    except WikiValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        current_app.logger.exception("Unexpected error creating wiki category")
        return jsonify({"error": str(exc)}), 500

    return jsonify({"category": result.category.to_dict()}), 201


@bp.route("/api/categories/<slug>", methods=["GET"])
@require_perms("wiki:read")
def api_category_detail(slug: str):
    """カテゴリ詳細API"""
    try:
        view_model = WikiCategoryDetailUseCase().execute(slug)
    except WikiPageNotFoundError:
        return jsonify({"error": "Category not found"}), 404
    return jsonify({
        "category": view_model.category.to_dict(),
        "pages": [p.to_dict() for p in view_model.pages],
    })


@bp.route("/api/admin", methods=["GET"])
@require_perms("wiki:admin")
def api_admin():
    """Wiki管理ダッシュボードAPI"""
    view_model = WikiAdminDashboardUseCase().execute()
    return jsonify({
        "total_pages": view_model.total_pages,
        "total_categories": view_model.total_categories,
        "recent_pages": [p.to_dict() for p in view_model.recent_pages],
    })

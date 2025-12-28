"""Wiki機能のWebルート"""

from __future__ import annotations

from flask import (
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_babel import _
from flask_login import current_user

from features.wiki.application.dto import (
    WikiCategoryCreateInput,
    WikiPageCreateInput,
    WikiPageDeleteInput,
    WikiPageUpdateInput,
)
from features.wiki.application.use_cases import (
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
    WikiPageSearchUseCase,
    WikiPageDeletionUseCase,
    WikiPageUpdateUseCase,
)
from core.models.authz import require_perms
from features.wiki.domain.exceptions import (
    WikiAccessDeniedError,
    WikiOperationError,
    WikiPageNotFoundError,
    WikiValidationError,
)
from webapp.security import get_or_set_csrf_token, validate_csrf_token

from . import bp


@bp.route("/")
@require_perms("wiki:read")
def index():
    """Wiki トップページ"""

    view_model = WikiIndexUseCase().execute()
    return render_template(
        "wiki/index.html",
        recent_pages=view_model.recent_pages,
        page_hierarchy=view_model.page_hierarchy,
        categories=view_model.categories,
    )


@bp.route("/page/<slug>")
@require_perms("wiki:read")
def view_page(slug: str):
    """Wikiページ表示"""

    try:
        view_model = WikiPageDetailUseCase().execute(slug)
    except WikiPageNotFoundError:
        abort(404)

    return render_template(
        "wiki/page.html",
        page=view_model.page,
        children=view_model.children,
        categories=view_model.categories,
        page_hierarchy=view_model.page_hierarchy,
        csrf_token=get_or_set_csrf_token(),
    )


@bp.route("/create", methods=["GET", "POST"])
@require_perms("wiki:write")
def create_page():
    """Wikiページ作成"""

    if request.method == "GET":
        form_data = WikiPageFormPreparationUseCase().execute()
        return render_template(
            "wiki/create.html",
            categories=form_data.categories,
            pages=form_data.pages,
        )

    payload = WikiPageCreateInput(
        title=request.form.get("title", ""),
        content=request.form.get("content", ""),
        slug=request.form.get("slug"),
        parent_id=request.form.get("parent_id"),
        category_ids=request.form.getlist("category_ids"),
        author_id=current_user.id,
    )

    try:
        result = WikiPageCreationUseCase().execute(payload)
    except WikiValidationError as exc:
        flash(str(exc), "error")
        return redirect(url_for("wiki.create_page"))
    except WikiOperationError as exc:
        flash(f"ページ作成エラー: {exc}", "error")
        return redirect(url_for("wiki.create_page"))
    except Exception as exc:  # noqa: BLE001 - 最終的なフォールバック
        flash(f"ページ作成エラー: {exc}", "error")
        return redirect(url_for("wiki.create_page"))

    flash("ページを作成しました", "success")
    return redirect(url_for("wiki.view_page", slug=result.page.slug))


@bp.route("/edit/<slug>", methods=["GET", "POST"])
@require_perms("wiki:write")
def edit_page(slug: str):
    """Wikiページ編集"""

    has_admin_rights = current_user.can("wiki:admin")

    if request.method == "GET":
        try:
            view_model = WikiPageEditPreparationUseCase().execute(
                slug=slug,
                user_id=current_user.id,
                has_admin_rights=has_admin_rights,
            )
        except WikiPageNotFoundError:
            abort(404)
        except WikiAccessDeniedError as exc:
            flash(str(exc), "error")
            return redirect(url_for("wiki.view_page", slug=slug))

        return render_template("wiki/edit.html", page=view_model.page, categories=view_model.categories)

    payload = WikiPageUpdateInput(
        slug=slug,
        title=request.form.get("title", ""),
        content=request.form.get("content", ""),
        change_summary=request.form.get("change_summary"),
        category_ids=request.form.getlist("category_ids"),
        editor_id=current_user.id,
        has_admin_rights=has_admin_rights,
    )

    try:
        result = WikiPageUpdateUseCase().execute(payload)
    except WikiPageNotFoundError:
        abort(404)
    except WikiAccessDeniedError as exc:
        flash(str(exc), "error")
        return redirect(url_for("wiki.view_page", slug=slug))
    except WikiValidationError as exc:
        flash(str(exc), "error")
        return redirect(url_for("wiki.edit_page", slug=slug))
    except WikiOperationError as exc:
        flash(str(exc), "error")
        return redirect(url_for("wiki.edit_page", slug=slug))
    except Exception as exc:  # noqa: BLE001 - 最終的なフォールバック
        flash(f"更新エラー: {exc}", "error")
        return redirect(url_for("wiki.edit_page", slug=slug))

    flash("ページを更新しました", "success")
    return redirect(url_for("wiki.view_page", slug=result.page.slug))


@bp.route("/page/<slug>/delete", methods=["POST"])
@require_perms("wiki:write")
def delete_page(slug: str):
    """Wikiページ削除"""

    if not validate_csrf_token(request.form.get("csrf_token")):
        current_app.logger.warning(
            "Rejected wiki page deletion due to invalid CSRF token",
            extra={"slug": slug},
        )
        flash(_("Security verification failed. Please reload the page and try again."), "error")
        return redirect(url_for("wiki.view_page", slug=slug))

    has_admin_rights = current_user.can("wiki:admin")
    payload = WikiPageDeleteInput(
        slug=slug,
        executor_id=current_user.id,
        has_admin_rights=has_admin_rights,
    )

    try:
        WikiPageDeletionUseCase().execute(payload)
    except WikiValidationError:
        flash(_("Page identifier is required."), "error")
        return redirect(url_for("wiki.view_page", slug=slug))
    except WikiPageNotFoundError:
        abort(404)
    except WikiAccessDeniedError:
        flash(_("You do not have permission to delete this page."), "error")
        return redirect(url_for("wiki.view_page", slug=slug))
    except WikiOperationError as exc:
        if str(exc) == "page_has_children":
            flash(_("Cannot delete a page that has child pages."), "error")
        else:
            flash(_("Failed to delete the page."), "error")
        return redirect(url_for("wiki.view_page", slug=slug))
    except Exception:  # noqa: BLE001 - フォールバック
        current_app.logger.exception("Unexpected error while deleting wiki page", extra={"slug": slug})
        flash(_("Failed to delete the page."), "error")
        return redirect(url_for("wiki.view_page", slug=slug))

    flash(_("Page deleted successfully."), "success")
    return redirect(url_for("wiki.index"))


@bp.route("/search")
@require_perms("wiki:read")
def search():
    """Wiki検索"""

    result = WikiPageSearchUseCase().execute(request.args.get("q", ""), limit=50)
    return render_template("wiki/search.html", pages=result.pages, query=result.query)


@bp.route("/category/<slug>")
@require_perms("wiki:read")
def view_category(slug: str):
    """カテゴリ別ページ一覧"""

    try:
        view_model = WikiCategoryDetailUseCase().execute(slug)
    except WikiPageNotFoundError:
        abort(404)

    return render_template("wiki/category.html", category=view_model.category, pages=view_model.pages)


@bp.route("/history/<slug>")
@require_perms("wiki:read")
def page_history(slug: str):
    """ページ履歴表示"""

    try:
        view_model = WikiPageHistoryUseCase().execute(slug, limit=50)
    except WikiPageNotFoundError:
        abort(404)

    return render_template("wiki/history.html", page=view_model.page, revisions=view_model.revisions)


@bp.route("/api/pages")
@require_perms("wiki:read")
def api_pages():
    """ページ一覧API"""

    result = WikiApiPagesUseCase().execute(limit=100)
    return jsonify({"pages": [page.to_dict() for page in result.pages]})


@bp.route("/api/search")
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


@bp.route("/categories")
@require_perms("wiki:read")
def categories():
    """カテゴリ一覧"""

    view_model = WikiCategoryListUseCase().execute()
    return render_template("wiki/categories.html", categories=view_model.categories)


@bp.route("/categories/create", methods=["GET", "POST"])
@require_perms("wiki:admin")
def create_category():
    """カテゴリ作成"""

    if request.method == "GET":
        return render_template("wiki/create_category.html")

    payload = WikiCategoryCreateInput(
        name=request.form.get("name", ""),
        description=request.form.get("description"),
        slug=request.form.get("slug"),
    )

    try:
        result = WikiCategoryCreationUseCase().execute(payload)
    except WikiValidationError as exc:
        flash(str(exc), "error")
        return redirect(url_for("wiki.create_category"))
    except Exception as exc:  # noqa: BLE001 - 最終的なフォールバック
        flash(f"カテゴリ作成エラー: {exc}", "error")
        return redirect(url_for("wiki.create_category"))

    flash("カテゴリを作成しました", "success")
    return redirect(url_for("wiki.view_category", slug=result.category.slug))


@bp.route("/admin")
@require_perms("wiki:admin")
def admin():
    """Wiki管理画面"""

    view_model = WikiAdminDashboardUseCase().execute()
    stats = {
        "total_pages": view_model.total_pages,
        "total_categories": view_model.total_categories,
        "recent_pages": view_model.recent_pages,
    }
    return render_template("wiki/admin.html", stats=stats)

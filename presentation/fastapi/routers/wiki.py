"""Wiki機能 FastAPI ルーター。

Flask版 ``bounded_contexts/wiki/presentation/wiki/routes.py`` を移植。
フロントエンドは ``baseURL: '/wiki/api'`` でアクセスする。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status

from shared.application.authenticated_principal import AuthenticatedPrincipal
from presentation.fastapi.dependencies.auth import get_current_principal, require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/wiki/api", tags=["wiki"])


# ---------------------------------------------------------------------------
# エンドポイント
# ---------------------------------------------------------------------------


@router.get("/index")
async def api_index(
    principal: AuthenticatedPrincipal = Depends(require_permission("wiki:read")),
):
    from bounded_contexts.wiki.application.use_cases import WikiIndexUseCase

    view_model = WikiIndexUseCase().execute()
    return {
        "recent_pages": [p.to_dict() for p in view_model.recent_pages],
        "page_hierarchy": view_model.page_hierarchy,
        "categories": [c.to_dict() for c in view_model.categories],
    }


@router.get("/pages")
async def api_pages(
    principal: AuthenticatedPrincipal = Depends(require_permission("wiki:read")),
):
    from bounded_contexts.wiki.application.use_cases import WikiApiPagesUseCase

    result = WikiApiPagesUseCase().execute(limit=100)
    return {"pages": [page.to_dict() for page in result.pages]}


@router.get("/pages/{slug}")
async def api_page_detail(
    slug: str,
    principal: AuthenticatedPrincipal = Depends(require_permission("wiki:read")),
):
    from bounded_contexts.wiki.application.use_cases import WikiPageDetailUseCase
    from bounded_contexts.wiki.domain.exceptions import WikiPageNotFoundError

    try:
        view_model = WikiPageDetailUseCase().execute(slug)
    except WikiPageNotFoundError:
        raise HTTPException(status_code=404, detail={"error": "Page not found"})
    return {
        "page": view_model.page.to_dict(),
        "children": view_model.children,
        "categories": [c.to_dict() for c in view_model.categories],
        "page_hierarchy": view_model.page_hierarchy,
    }


@router.get("/create-form")
async def api_create_form(
    principal: AuthenticatedPrincipal = Depends(require_permission("wiki:write")),
):
    from bounded_contexts.wiki.application.use_cases import WikiPageFormPreparationUseCase

    form_data = WikiPageFormPreparationUseCase().execute()
    return {
        "categories": [c.to_dict() for c in form_data.categories],
        "pages": [p.to_dict() for p in form_data.pages],
    }


@router.post("/pages", status_code=status.HTTP_201_CREATED)
async def api_create_page(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_permission("wiki:write")),
):
    from bounded_contexts.wiki.application.dto import WikiPageCreateInput
    from bounded_contexts.wiki.application.use_cases import WikiPageCreationUseCase
    from bounded_contexts.wiki.domain.exceptions import WikiOperationError, WikiValidationError

    data = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    category_ids = data.get("category_ids", [])
    if isinstance(category_ids, str):
        category_ids = [category_ids] if category_ids else []
    payload = WikiPageCreateInput(
        title=data.get("title", ""),
        content=data.get("content", ""),
        slug=data.get("slug") or None,
        parent_id=data.get("parent_id") or None,
        category_ids=category_ids,
        author_id=int(principal.subject_id),
    )
    try:
        result = WikiPageCreationUseCase().execute(payload)
    except WikiValidationError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)})
    except WikiOperationError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)})
    except Exception as exc:
        logger.exception("Unexpected error creating wiki page")
        raise HTTPException(status_code=500, detail={"error": str(exc)})
    return {"page": result.page.to_dict()}


@router.get("/pages/{slug}/edit-form")
async def api_edit_form(
    slug: str,
    principal: AuthenticatedPrincipal = Depends(require_permission("wiki:write")),
):
    from bounded_contexts.wiki.application.use_cases import WikiPageEditPreparationUseCase
    from bounded_contexts.wiki.domain.exceptions import WikiAccessDeniedError, WikiPageNotFoundError

    has_admin_rights = principal.can("wiki:admin")
    try:
        view_model = WikiPageEditPreparationUseCase().execute(
            slug=slug,
            user_id=int(principal.subject_id),
            has_admin_rights=has_admin_rights,
        )
    except WikiPageNotFoundError:
        raise HTTPException(status_code=404, detail={"error": "Page not found"})
    except WikiAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail={"error": str(exc)})
    return {
        "page": view_model.page.to_dict(),
        "categories": [c.to_dict() for c in view_model.categories],
    }


@router.patch("/pages/{slug}")
async def api_update_page(
    slug: str,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_permission("wiki:write")),
):
    from bounded_contexts.wiki.application.dto import WikiPageUpdateInput
    from bounded_contexts.wiki.application.use_cases import WikiPageUpdateUseCase
    from bounded_contexts.wiki.domain.exceptions import (
        WikiAccessDeniedError,
        WikiOperationError,
        WikiPageNotFoundError,
        WikiValidationError,
    )

    data = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    has_admin_rights = principal.can("wiki:admin")
    category_ids = data.get("category_ids", [])
    if isinstance(category_ids, str):
        category_ids = [category_ids] if category_ids else []
    payload = WikiPageUpdateInput(
        slug=slug,
        title=data.get("title", ""),
        content=data.get("content", ""),
        change_summary=data.get("change_summary") or None,
        category_ids=category_ids,
        editor_id=int(principal.subject_id),
        has_admin_rights=has_admin_rights,
    )
    try:
        result = WikiPageUpdateUseCase().execute(payload)
    except WikiPageNotFoundError:
        raise HTTPException(status_code=404, detail={"error": "Page not found"})
    except WikiAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail={"error": str(exc)})
    except WikiValidationError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)})
    except WikiOperationError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)})
    except Exception as exc:
        logger.exception("Unexpected error updating wiki page")
        raise HTTPException(status_code=500, detail={"error": str(exc)})
    return {"page": result.page.to_dict()}


@router.delete("/pages/{slug}")
async def api_delete_page(
    slug: str,
    principal: AuthenticatedPrincipal = Depends(require_permission("wiki:write")),
):
    from bounded_contexts.wiki.application.dto import WikiPageDeleteInput
    from bounded_contexts.wiki.application.use_cases import WikiPageDeletionUseCase
    from bounded_contexts.wiki.domain.exceptions import (
        WikiAccessDeniedError,
        WikiOperationError,
        WikiPageNotFoundError,
        WikiValidationError,
    )

    has_admin_rights = principal.can("wiki:admin")
    payload = WikiPageDeleteInput(
        slug=slug,
        executor_id=int(principal.subject_id),
        has_admin_rights=has_admin_rights,
    )
    try:
        WikiPageDeletionUseCase().execute(payload)
    except WikiValidationError:
        raise HTTPException(status_code=400, detail={"error": "Page identifier is required"})
    except WikiPageNotFoundError:
        raise HTTPException(status_code=404, detail={"error": "Page not found"})
    except WikiAccessDeniedError:
        raise HTTPException(status_code=403, detail={"error": "Permission denied"})
    except WikiOperationError as exc:
        if str(exc) == "page_has_children":
            raise HTTPException(status_code=400, detail={"error": "Cannot delete a page that has child pages"})
        raise HTTPException(status_code=400, detail={"error": "Failed to delete the page"})
    except Exception:
        logger.exception("Unexpected error deleting wiki page", extra={"slug": slug})
        raise HTTPException(status_code=500, detail={"error": "Failed to delete the page"})
    return {"deleted": True, "slug": slug}


@router.get("/pages/{slug}/history")
async def api_page_history(
    slug: str,
    principal: AuthenticatedPrincipal = Depends(require_permission("wiki:read")),
):
    from bounded_contexts.wiki.application.use_cases import WikiPageHistoryUseCase
    from bounded_contexts.wiki.domain.exceptions import WikiPageNotFoundError

    try:
        view_model = WikiPageHistoryUseCase().execute(slug, limit=50)
    except WikiPageNotFoundError:
        raise HTTPException(status_code=404, detail={"error": "Page not found"})
    return {
        "page": view_model.page.to_dict(),
        "revisions": [r.to_dict() for r in view_model.revisions],
    }


@router.get("/search")
async def api_search(
    q: str = Query(""),
    limit: int = Query(20, ge=1, le=100),
    principal: AuthenticatedPrincipal = Depends(require_permission("wiki:read")),
):
    from bounded_contexts.wiki.application.use_cases import WikiApiSearchUseCase

    result = WikiApiSearchUseCase().execute(q, limit=min(limit, 100))
    return {
        "pages": [page.to_dict() for page in result.pages],
        "query": result.query,
    }


@router.post("/preview")
async def api_preview(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_permission("wiki:read")),
):
    from bounded_contexts.wiki.application.use_cases import WikiMarkdownPreviewUseCase

    payload = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    content = payload.get("content", "")
    result = WikiMarkdownPreviewUseCase().execute(content)
    return {"html": result.html}


@router.get("/categories")
async def api_categories(
    principal: AuthenticatedPrincipal = Depends(require_permission("wiki:read")),
):
    from bounded_contexts.wiki.application.use_cases import WikiCategoryListUseCase

    view_model = WikiCategoryListUseCase().execute()
    return {
        "categories": [
            {**item.category.to_dict(), "page_count": item.page_count}
            for item in view_model.categories
        ]
    }


@router.post("/categories", status_code=status.HTTP_201_CREATED)
async def api_create_category(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_permission("wiki:admin")),
):
    from bounded_contexts.wiki.application.dto import WikiCategoryCreateInput
    from bounded_contexts.wiki.application.use_cases import WikiCategoryCreationUseCase
    from bounded_contexts.wiki.domain.exceptions import WikiValidationError

    data = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    payload = WikiCategoryCreateInput(
        name=data.get("name", ""),
        description=data.get("description") or None,
        slug=data.get("slug") or None,
    )
    try:
        result = WikiCategoryCreationUseCase().execute(payload)
    except WikiValidationError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)})
    except Exception as exc:
        logger.exception("Unexpected error creating wiki category")
        raise HTTPException(status_code=500, detail={"error": str(exc)})
    return {"category": result.category.to_dict()}


@router.get("/categories/{slug}")
async def api_category_detail(
    slug: str,
    principal: AuthenticatedPrincipal = Depends(require_permission("wiki:read")),
):
    from bounded_contexts.wiki.application.use_cases import WikiCategoryDetailUseCase
    from bounded_contexts.wiki.domain.exceptions import WikiPageNotFoundError

    try:
        view_model = WikiCategoryDetailUseCase().execute(slug)
    except WikiPageNotFoundError:
        raise HTTPException(status_code=404, detail={"error": "Category not found"})
    return {
        "category": view_model.category.to_dict(),
        "pages": [p.to_dict() for p in view_model.pages],
    }


@router.get("/admin")
async def api_admin(
    principal: AuthenticatedPrincipal = Depends(require_permission("wiki:admin")),
):
    from bounded_contexts.wiki.application.use_cases import WikiAdminDashboardUseCase

    view_model = WikiAdminDashboardUseCase().execute()
    return {
        "total_pages": view_model.total_pages,
        "total_categories": view_model.total_categories,
        "recent_pages": [p.to_dict() for p in view_model.recent_pages],
    }


__all__ = ["router"]

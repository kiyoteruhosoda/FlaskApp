"""FastAPI JWT 認証依存コンポーネント。

Flask-Login の ``login_required`` / ``current_user`` に相当する
FastAPI ``Depends()`` ベースの認証依存を提供する。
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.kernel.database.session import get_db

logger = logging.getLogger(__name__)

# アクセストークンを格納する Cookie 名（ログイン時に auth ルーターが設定する）
ACCESS_TOKEN_COOKIE = "access_token"

# Cookie または Authorization ヘッダーからトークンを取得する
# auto_error=False にして手動でクッキーフォールバックを行う
_bearer_scheme = HTTPBearer(auto_error=False)


def _extract_token(
    credentials: Optional[HTTPAuthorizationCredentials],
    access_token_cookie: Optional[str] = None,
) -> Optional[str]:
    """Authorization ヘッダー優先、無ければ Cookie からアクセストークンを取得する。

    ``<img src="/api/dl/...">`` のようにブラウザが Authorization ヘッダーを
    付与できないリクエストでは、ログイン時に設定される ``access_token`` Cookie を
    フォールバックとして利用する（Flask 版の ``login_or_jwt_required`` 相当）。
    """
    if credentials and credentials.scheme.lower() == "bearer":
        return credentials.credentials
    if access_token_cookie:
        return access_token_cookie
    return None


async def get_current_principal(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    access_token_cookie: Optional[str] = Cookie(
        default=None, alias=ACCESS_TOKEN_COOKIE
    ),
    db: Session = Depends(get_db),
) -> AuthenticatedPrincipal:
    """JWT を検証して ``AuthenticatedPrincipal`` を返す依存関数。

    認証失敗時は ``HTTP 401`` を送出する。
    """
    from presentation.fastapi.services.token_service import TokenService

    token = _extract_token(credentials, access_token_cookie)

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "authentication_required"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    principal, reason = TokenService.verify_access_token_with_reason(token, session=db)
    if not principal:
        logger.debug("JWT 認証失敗: %s", reason)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "reason": reason},
            headers={"WWW-Authenticate": "Bearer"},
        )

    return principal


async def get_optional_principal(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    access_token_cookie: Optional[str] = Cookie(
        default=None, alias=ACCESS_TOKEN_COOKIE
    ),
    db: Session = Depends(get_db),
) -> Optional[AuthenticatedPrincipal]:
    """Authorization ヘッダーまたは Cookie から JWT を検証する。

    認証失敗時は ``None`` を返す（例外は送出しない）。
    """
    from presentation.fastapi.services.token_service import TokenService

    token = _extract_token(credentials, access_token_cookie)
    if not token:
        return None

    return TokenService.create_principal_from_token(token, session=db)


def require_permission(*codes: str):
    """指定された権限を全て保持している場合のみアクセスを許可する依存関数ファクトリ。

    使用例::

        @router.get("/admin/users")
        def list_users(
            principal: AuthenticatedPrincipal = Depends(require_permission("user:manage")),
        ):
            ...
    """
    async def _check(
        principal: AuthenticatedPrincipal = Depends(get_current_principal),
    ) -> AuthenticatedPrincipal:
        if not principal.can(*codes):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "forbidden",
                    "message": f"Required permissions: {', '.join(codes)}",
                },
            )
        return principal

    return _check


def require_any_permission(*codes: str):
    """指定された権限のいずれかを保持している場合のみアクセスを許可する依存関数ファクトリ。"""

    async def _check(
        principal: AuthenticatedPrincipal = Depends(get_current_principal),
    ) -> AuthenticatedPrincipal:
        if not any(c in principal.permissions for c in codes):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "forbidden",
                    "message": f"One of the following permissions is required: {', '.join(codes)}",
                },
            )
        return principal

    return _check


__all__ = [
    "get_current_principal",
    "get_optional_principal",
    "require_permission",
    "require_any_permission",
]


"""ユーザー設定 API（FastAPI）。

Flask-Smorest 版 ``presentation/web/api/user_preferences.py`` を移植。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.kernel.database.session import get_db
from presentation.fastapi.dependencies.auth import get_current_principal

router = APIRouter(prefix="/user/preferences", tags=["user"])

# 更新を許可するキーと各バリデーター
_ALLOWED_KEYS: dict[str, tuple[type, object]] = {}


def _load_allowed_keys() -> dict:
    """遅延インポートで許可キーを取得する。"""
    from shared.infrastructure.models.user_preference import UserPreference

    return {
        UserPreference.KEY_SLIDESHOW_INTERVAL: (int, lambda v: 1 <= v <= 300),
    }


@router.get("", response_model=dict)
async def api_user_preferences_get(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """現在のユーザーの設定を返す（未設定項目はデフォルト値で補完）。"""
    from shared.infrastructure.models.user_preference import UserPreference

    if not principal.is_individual:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "authentication_required"},
        )

    prefs = UserPreference.get_all_for_user(principal.id)
    return {"preferences": prefs}


@router.put("", response_model=dict)
async def api_user_preferences_update(
    payload: dict,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """現在のユーザーの設定を更新する。"""
    from shared.infrastructure.models.user_preference import UserPreference

    if not principal.is_individual:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "authentication_required"},
        )

    allowed_keys = _load_allowed_keys()
    updated_keys: list[str] = []

    for key, raw_value in payload.items():
        if key not in allowed_keys:
            continue

        expected_type, validator = allowed_keys[key]
        try:
            value = expected_type(raw_value)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "invalid_value",
                    "key": key,
                    "message": f"Value for '{key}' must be {expected_type.__name__}.",
                },
            )

        if callable(validator) and not validator(value):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "value_out_of_range",
                    "key": key,
                    "message": f"Value for '{key}' is out of allowed range.",
                },
            )

        UserPreference.set_for_user(principal.id, key, value)
        updated_keys.append(key)

    if updated_keys:
        db.commit()

    prefs = UserPreference.get_all_for_user(principal.id)
    return {"preferences": prefs, "updated": updated_keys}

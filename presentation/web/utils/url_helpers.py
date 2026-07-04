from __future__ import annotations

"""Helpers for building externally visible URLs."""

from urllib.parse import urlsplit

from flask import Request, current_app, request, url_for

from shared.kernel.settings.settings import settings

# Google OAuth コールバックの Flask エンドポイント。
# コールバックのパスはこのルートで固定されており、設定では変更できない。
GOOGLE_OAUTH_CALLBACK_ENDPOINT = "auth.google_oauth_callback"


def _extract_forwarded_proto(forwarded_header: str | None) -> str | None:
    """Parse the ``Forwarded`` header and return the ``proto`` value if present."""

    if not forwarded_header:
        return None

    for part in forwarded_header.split(","):
        for attribute in part.split(";"):
            attribute = attribute.strip()
            if attribute.lower().startswith("proto="):
                value = attribute.split("=", 1)[1].strip().strip('"')
                if value:
                    return value.strip().lower()
    return None


def _extract_x_forwarded_proto(header_value: str | None) -> str | None:
    """Return the first protocol value from ``X-Forwarded-Proto`` if available."""

    if not header_value:
        return None

    proto = header_value.split(",")[0].strip()
    if proto:
        return proto.lower()
    return None


def determine_external_scheme(req: Request | None = None) -> str:
    """Return the preferred scheme when generating external URLs.

    The resolution order matches production expectations:

    1. Persisted application setting ``PREFERRED_URL_SCHEME`` (manual override).
    2. ``Forwarded`` header ``proto`` attribute.
    3. ``X-Forwarded-Proto`` header.
    4. The request's ``scheme``/``wsgi.url_scheme``.
    5. Fallback to ``https`` to avoid downgrading OAuth redirects.
    """

    req = req or request

    preferred_scheme = settings.preferred_url_scheme
    if preferred_scheme:
        scheme = str(preferred_scheme).strip().lower()
        if scheme:
            return scheme

    forwarded_proto = _extract_forwarded_proto(req.headers.get("Forwarded"))
    if forwarded_proto:
        return forwarded_proto

    x_forwarded_proto = _extract_x_forwarded_proto(req.headers.get("X-Forwarded-Proto"))
    if x_forwarded_proto:
        return x_forwarded_proto

    env_scheme = getattr(req, "scheme", None) or req.environ.get("wsgi.url_scheme")
    if env_scheme:
        return str(env_scheme).strip().lower()

    return "https"


def google_oauth_callback_path() -> str:
    """Return the fixed URL path of the Google OAuth callback route."""

    # url_for は PREFERRED_URL_SCHEME が空文字のときフル URL を返すことが
    # あるため、URL マップからルート定義（変数なしの静的パス）を直接引く。
    rule = next(current_app.url_map.iter_rules(GOOGLE_OAUTH_CALLBACK_ENDPOINT))
    return rule.rule


def validate_google_oauth_redirect_origin(value: str) -> str | None:
    """Validate a GOOGLE_OAUTH_REDIRECT_ORIGIN value.

    設定値はスキームとホストのみ（例 ``https://photos.example.com``）。
    コールバックのパスは Flask ルートで固定のため含めない。
    妥当なら ``None``、不正なら理由（英語）を返す。
    """

    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return "must be an absolute http(s) origin (scheme and host)"
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        return "must contain only the scheme and host (no path, query or fragment)"
    return None


def _redirect_origin_or_none(raw: str) -> str | None:
    """設定値からオリジン（scheme://host）を取り出す。不正なら ``None``。

    旧設定 ``GOOGLE_OAUTH_REDIRECT_URI``（固定パス込みのフル URL）も
    後方互換としてオリジン部分を取り出して受け付ける。
    """

    parts = urlsplit(raw)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    if parts.query or parts.fragment:
        return None
    if parts.path in ("", "/") or parts.path == google_oauth_callback_path():
        return f"{parts.scheme}://{parts.netloc}"
    return None


def google_oauth_callback_url() -> str:
    """Return the external Google OAuth callback URL (redirect_uri).

    パスは Flask ルート（``/auth/google/callback``）で固定。設定
    ``GOOGLE_OAUTH_REDIRECT_ORIGIN`` があればそのスキーム・ホストに固定パスを
    連結し、不正な値は警告ログを出して無視する。未設定・無効時は
    リクエストのホストと ``determine_external_scheme()`` から自動生成する。
    認可リクエストとトークン交換の両方で必ずこの関数を使うこと（redirect_uri は
    両者で完全一致が必要）。
    """

    configured = settings.google_oauth_redirect_origin
    if configured:
        origin = _redirect_origin_or_none(configured)
        if origin:
            return origin + google_oauth_callback_path()
        current_app.logger.warning(
            "Ignoring GOOGLE_OAUTH_REDIRECT_ORIGIN %r: must contain only the "
            "scheme and host (e.g. https://example.com). "
            "Falling back to the auto-derived callback URL.",
            configured,
        )

    return url_for(
        GOOGLE_OAUTH_CALLBACK_ENDPOINT,
        _external=True,
        _scheme=determine_external_scheme(),
    )


__all__ = [
    "determine_external_scheme",
    "google_oauth_callback_path",
    "google_oauth_callback_url",
    "validate_google_oauth_redirect_origin",
]

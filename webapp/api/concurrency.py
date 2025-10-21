"""Concurrency control utilities for API endpoints.

このモジュールはAPI毎に同時実行数を制御するための共通処理を提供する。
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from functools import wraps
from threading import Lock
from typing import Callable, Optional, TypeVar, Any, cast

from flask import jsonify

from core.settings import settings


class ConcurrencyLimitExceeded(RuntimeError):
    """Raised when the concurrency limiter cannot acquire a slot."""

    def __init__(self, retry_after: float) -> None:
        super().__init__("Concurrency limit exceeded")
        self.retry_after = retry_after


@dataclass(frozen=True)
class ConcurrencyConfig:
    """Configuration keys used by :class:`ConcurrencyLimiter`."""

    limit_key: str
    retry_key: Optional[str] = None
    default_limit: int = 3
    default_retry: float = 1.0


class ConcurrencyLimiter(AbstractContextManager["ConcurrencyLimiter"]):
    """Track active calls and enforce a configurable concurrency ceiling."""

    def __init__(self, config: ConcurrencyConfig) -> None:
        self._config = config
        self._active = 0
        self._guard = Lock()

    # --- Internal helpers -------------------------------------------------
    def _configured_limit(self) -> int:
        limit = settings.concurrency.limit(
            self._config.limit_key, self._config.default_limit
        )
        return max(1, limit)

    def _configured_retry(self) -> float:
        retry = settings.concurrency.retry(
            self._config.retry_key, self._config.default_retry
        )
        return max(0.0, retry)

    # --- Public API -------------------------------------------------------
    def acquire(self) -> bool:
        """Attempt to acquire a concurrency slot without blocking."""

        with self._guard:
            limit = self._configured_limit()
            if self._active >= limit:
                return False
            self._active += 1
            return True

    def release(self) -> None:
        """Release a previously acquired slot (if any)."""

        with self._guard:
            if self._active > 0:
                self._active -= 1

    # Context manager support ---------------------------------------------
    def __enter__(self) -> "ConcurrencyLimiter":
        if not self.acquire():
            raise ConcurrencyLimitExceeded(self.retry_after_seconds())
        return self

    def __exit__(self, exc_type, exc, tb) -> Optional[bool]:  # pragma: no cover -
        self.release()
        return None

    # Utility accessors ----------------------------------------------------
    def retry_after_seconds(self) -> float:
        return self._configured_retry()

    def retry_after_header(self, retry_after: Optional[float] = None) -> Optional[str]:
        value = self.retry_after_seconds() if retry_after is None else retry_after
        try:
            seconds = max(0, int(round(float(value))))
        except (TypeError, ValueError):  # pragma: no cover - defensive
            return None
        return str(seconds)


F = TypeVar("F", bound=Callable[..., Any])


def limit_concurrency(limiter: ConcurrencyLimiter) -> Callable[[F], F]:
    """Decorator that enforces concurrency for an API endpoint."""

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any):  # type: ignore[misc]
            try:
                with limiter:
                    return func(*args, **kwargs)
            except ConcurrencyLimitExceeded as exc:
                payload = {"error": "rate_limited", "retryAfter": exc.retry_after}
                response = jsonify(payload)
                header_value = limiter.retry_after_header(exc.retry_after)
                if header_value is not None:
                    response.headers["Retry-After"] = header_value
                return response, 429

        return cast(F, wrapper)

    return decorator


def create_limiter(
    prefix: str,
    *,
    limit_suffix: str = "_MAX_CONCURRENCY",
    retry_suffix: str = "_RETRY_AFTER_SECONDS",
    default_limit: int = 3,
    default_retry: float = 1.0,
) -> ConcurrencyLimiter:
    """Convenience factory that derives config keys from a prefix."""

    config = ConcurrencyConfig(
        limit_key=f"{prefix}{limit_suffix}",
        retry_key=f"{prefix}{retry_suffix}" if retry_suffix else None,
        default_limit=default_limit,
        default_retry=default_retry,
    )
    return ConcurrencyLimiter(config)


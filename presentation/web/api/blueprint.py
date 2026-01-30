"""Blueprint utilities for API authentication enforcement."""
from __future__ import annotations

from collections.abc import Iterable
import inspect
from typing import Callable

from flask.views import MethodView
from flask_smorest import Blueprint as SmorestBlueprint


def _iter_wrapped(callable_obj: Callable) -> Iterable[Callable]:
    """Yield the callable and all wrappers referenced via ``__wrapped__``."""

    current = callable_obj
    seen: set[Callable] = set()
    while current and current not in seen:
        yield current
        seen.add(current)
        current = getattr(current, "__wrapped__", None)


def _has_auth_marker(func: Callable) -> bool:
    """Return ``True`` if the callable declares an authentication marker."""

    for candidate in _iter_wrapped(func):
        if getattr(candidate, "_skip_auth", False):
            return True
        if getattr(candidate, "_auth_enforced", False):
            return True
    return False


class AuthEnforcedBlueprint(SmorestBlueprint):
    """Blueprint that rejects routes without explicit auth configuration."""

    def add_url_rule(  # type: ignore[override]
        self,
        rule,
        endpoint=None,
        view_func=None,
        provide_automatic_options=None,
        *,
        parameters=None,
        tags=None,
        **options,
    ):
        if view_func is None:
            raise TypeError("view_func must be provided")

        self._ensure_authentication_marker(rule, endpoint, view_func)

        return super().add_url_rule(  # pragma: no cover - exercised via decorators
            rule,
            endpoint=endpoint,
            view_func=view_func,
            provide_automatic_options=provide_automatic_options,
            parameters=parameters,
            tags=tags,
            **options,
        )

    def _ensure_authentication_marker(self, rule, endpoint, view_func) -> None:
        """Ensure that the registered view declares an auth strategy."""

        candidates: list[Callable]

        if inspect.isclass(view_func) and issubclass(view_func, MethodView):
            name = endpoint or view_func.__name__
            view_callable = view_func.as_view(name)
            candidates = [view_callable]
        else:
            candidates = [view_func]

        for func in candidates:
            if _has_auth_marker(func):
                return

        view_name = endpoint or getattr(view_func, "__name__", "<unnamed>")
        raise RuntimeError(
            f"API route '{rule}' (endpoint '{view_name}') must declare an authentication decorator."
        )


__all__ = ["AuthEnforcedBlueprint"]


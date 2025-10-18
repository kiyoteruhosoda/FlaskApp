"""OpenAPIエンドポイントとSwagger UIを提供するモジュール。"""

from __future__ import annotations

import inspect
import re
from collections import OrderedDict
from typing import Iterable

from flask import current_app, jsonify, render_template, request, url_for
from flask_babel import gettext as _

from . import bp


_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
_PATH_PARAMETER_PATTERN = re.compile(r"<(?:[^:<>]+:)?([^<>]+)>")
_EXCLUDED_ENDPOINTS = {"api.openapi_spec", "api.swagger_ui"}

_CONVERTER_SCHEMA_OVERRIDES = {
    "IntegerConverter": {"type": "integer"},
    "FloatConverter": {"type": "number"},
    "UUIDConverter": {"type": "string", "format": "uuid"},
}


def _convert_rule_to_openapi_path(rule) -> str:
    """FlaskのURLルールをOpenAPI互換のパス形式へ変換する。"""

    return _PATH_PARAMETER_PATTERN.sub(r"{\1}", rule.rule)


def _operation_docs(view_func) -> tuple[str | None, str | None]:
    """ビューのdocstringからsummary/descriptionを抽出する。"""

    if view_func is None:
        return None, None
    doc = inspect.getdoc(view_func)
    if not doc:
        return None, None
    lines = [line.strip() for line in doc.splitlines() if line.strip()]
    if not lines:
        return None, None
    summary = lines[0]
    description_lines = lines[1:]
    description = "\n".join(description_lines).strip() if description_lines else None
    return summary, description or None


def _derive_tag(path: str) -> str | None:
    """パスから最上位セグメントをタグ名として推定する。"""

    segments = [segment for segment in path.split("/") if segment]
    if segments and segments[0] == "api":
        segments = segments[1:]
    for segment in segments:
        if segment.startswith("{"):
            continue
        label = segment.replace("-", " ").replace("_", " ")
        label = label.title()
        return label
    return None


def _build_parameters(rule) -> list[dict]:
    """FlaskルールからOpenAPIのパスパラメータ定義を生成する。"""

    parameters: list[dict] = []
    arguments = sorted(rule.arguments)
    if not arguments:
        return parameters

    converters = getattr(rule, "_converters", {})
    for argument in arguments:
        converter = converters.get(argument)
        schema = {"type": "string"}
        if converter is not None:
            override = _CONVERTER_SCHEMA_OVERRIDES.get(type(converter).__name__)
            if override:
                schema = override.copy()
        parameters.append(
            {
                "name": argument,
                "in": "path",
                "required": True,
                "schema": schema,
            }
        )
    return parameters


def _iter_api_rules() -> Iterable:
    """OpenAPIに含めるFlaskルールを抽出する。"""

    rules = sorted(current_app.url_map.iter_rules(), key=lambda rule: rule.rule)
    for rule in rules:
        if not rule.rule.startswith("/api"):
            continue
        if rule.endpoint in _EXCLUDED_ENDPOINTS:
            continue
        if rule.endpoint == "static":
            continue
        yield rule


def _build_paths() -> OrderedDict:
    """OpenAPI pathsセクションを構築する。"""

    paths: dict[str, dict] = {}
    for rule in _iter_api_rules():
        methods = sorted(method for method in rule.methods if method in _HTTP_METHODS)
        if not methods:
            continue
        openapi_path = _convert_rule_to_openapi_path(rule)
        path_item = paths.setdefault(openapi_path, {})
        view_func = current_app.view_functions.get(rule.endpoint)
        summary, description = _operation_docs(view_func)
        tag = _derive_tag(openapi_path)
        parameters = _build_parameters(rule)
        for method in methods:
            operation: dict[str, object] = {
                "operationId": f"{rule.endpoint.replace('.', '_')}_{method.lower()}",
                "responses": {
                    "200": {"description": _("Successful response")},
                },
            }
            if summary:
                operation["summary"] = summary
            else:
                operation["summary"] = f"{method.title()} {openapi_path}"
            if description:
                operation["description"] = description
            if tag:
                operation["tags"] = [tag]
            if parameters:
                operation["parameters"] = parameters
            path_item[method.lower()] = operation
    ordered_paths = OrderedDict(sorted(paths.items()))
    return ordered_paths


@bp.get("/openapi.json")
def openapi_spec():
    """OpenAPI仕様ドキュメントを生成して返す。"""

    spec = {
        "openapi": "3.0.3",
        "info": {"title": f"{_('AppName')} API", "version": "1.0.0"},
        "servers": [{"url": request.url_root.rstrip("/")}],
        "paths": _build_paths(),
        "components": {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                },
                "cookieAuth": {
                    "type": "apiKey",
                    "in": "cookie",
                    "name": "access_token",
                },
            }
        },
    }
    return jsonify(spec)


@bp.get("/docs")
def swagger_ui():
    """Swagger UIを提供する。"""

    return render_template("swagger_ui.html", spec_url=url_for("api.openapi_spec"))

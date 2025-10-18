"""OpenAPIエンドポイントとSwagger UIを提供するモジュール。"""

from __future__ import annotations

import inspect
import re
from collections import OrderedDict
from typing import Iterable

from flask import current_app, jsonify, render_template, request, url_for
from flask_babel import gettext as _
from urllib.parse import urlsplit

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


def _resolve_server_urls() -> list[str]:
    """リバースプロキシ環境を考慮して外部公開URL候補を推測する。"""

    def _split_path_segments(value: str | None) -> list[str]:
        if not value:
            return []
        return [segment for segment in value.split("/") if segment]

    def _sanitize(value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if cleaned.startswith('"') and cleaned.endswith('"') and len(cleaned) >= 2:
            cleaned = cleaned[1:-1]
        return cleaned

    def _iter_forwarded_header_candidates() -> list[tuple[str | None, str | None]]:
        header_value = request.headers.get("Forwarded")
        if not header_value:
            return []
        candidates: list[tuple[str | None, str | None]] = []
        for part in header_value.split(","):
            part = part.strip()
            if not part:
                continue
            params: dict[str, str] = {}
            for pair in part.split(";"):
                pair = pair.strip()
                if not pair or "=" not in pair:
                    continue
                key, raw_value = pair.split("=", 1)
                params[key.lower()] = _sanitize(raw_value) or ""
            proto = params.get("proto") or None
            host = params.get("host") or None
            candidates.append((proto, host))
        return candidates

    def _determine_path_prefix() -> str:
        prefix_header = request.headers.get("X-Forwarded-Prefix")
        if prefix_header:
            raw_prefix = prefix_header.split(",")[0].strip()
            if "://" in raw_prefix:
                parsed_prefix = urlsplit(raw_prefix)
                raw_prefix = parsed_prefix.path or ""
        else:
            raw_prefix = ""
        prefix_segments = _split_path_segments(raw_prefix)

        script_root_segments = _split_path_segments(request.script_root)

        if prefix_segments:
            combined_segments = prefix_segments.copy()
            if script_root_segments:
                if not (
                    len(prefix_segments) >= len(script_root_segments)
                    and prefix_segments[-len(script_root_segments) :] == script_root_segments
                ):
                    overlap = 0
                    max_overlap = min(len(prefix_segments), len(script_root_segments))
                    for size in range(max_overlap, 0, -1):
                        if prefix_segments[-size:] == script_root_segments[:size]:
                            overlap = size
                            break
                    combined_segments.extend(script_root_segments[overlap:])
        else:
            combined_segments = script_root_segments

        if combined_segments:
            return "/" + "/".join(combined_segments)
        return ""

    path_prefix = _determine_path_prefix()

    forwarded_proto = request.headers.get("X-Forwarded-Proto")
    forwarded_host = request.headers.get("X-Forwarded-Host")
    forwarded_port = request.headers.get("X-Forwarded-Port")

    candidates: list[tuple[str | None, str | None, str | None]] = []
    for proto, host in _iter_forwarded_header_candidates():
        candidates.append((proto, host, None))

    if forwarded_proto or forwarded_host or forwarded_port:
        proto_candidate = forwarded_proto.split(",")[0].strip() if forwarded_proto else None
        host_candidate = forwarded_host.split(",")[0].strip() if forwarded_host else None
        port_candidate = forwarded_port.split(",")[0].strip() if forwarded_port else None
        candidates.append((proto_candidate, host_candidate, port_candidate))

    candidates.append((request.scheme, request.host, None))

    seen: set[str] = set()
    urls: list[str] = []
    for proto, host, port in candidates:
        scheme = (proto or request.scheme).lower()
        normalized_host = _sanitize(host) or request.host
        if port and ":" not in normalized_host:
            if not (
                (scheme == "http" and port == "80")
                or (scheme == "https" and port == "443")
            ):
                normalized_host = f"{normalized_host}:{port}"
        url = f"{scheme}://{normalized_host}{path_prefix}".rstrip("/")
        if url not in seen:
            urls.append(url)
            seen.add(url)

    return urls


@bp.get("/openapi.json")
def openapi_spec():
    """OpenAPI仕様ドキュメントを生成して返す。"""

    spec = {
        "openapi": "3.0.3",
        "info": {"title": f"{_('AppName')} API", "version": "1.0.0"},
        "servers": [{"url": url} for url in _resolve_server_urls()],
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

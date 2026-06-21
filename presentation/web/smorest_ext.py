"""flask-smorest のアプリ固有拡張.

pip パッケージ ``flask-smorest`` をベースに、本プロジェクトで必要な以下の
カスタマイズをアプリ層で提供する（本体をフォークせずに済ませるための層）。

- ``Error`` スキーマをフィールド単位の検証メッセージ（``{field: [msg, ...]}``）
  として OpenAPI に公開する :class:`ErrorSchema`
- エンドポイント一覧をインタラクティブな HTML テーブルで表示する
  ``/api/overview``（:meth:`Api.render_openapi_overview`）

Swagger UI の favicon・バージョン表示は ``presentation/web/templates`` に置いた
``swagger_ui.html`` がアプリテンプレートとして flask-smorest の同名テンプレートを
上書きすることで実現している。
"""

from __future__ import annotations

import flask
import marshmallow as ma
from flask_smorest import Api as _BaseApi


class ErrorSchema(ma.Schema):
    """OpenAPI に公開するエラーレスポンススキーマ.

    flask-smorest 既定の ``errors`` は単なる ``Dict`` だが、本 API は
    フィールド名ごとに検証メッセージの配列を返すため、その構造を明示する。
    """

    code = ma.fields.Integer(metadata={"description": "Error code"})
    status = ma.fields.String(metadata={"description": "Error status"})
    message = ma.fields.String(metadata={"description": "Error message"})
    errors = ma.fields.Dict(
        keys=ma.fields.String(),
        values=ma.fields.List(
            ma.fields.String(),
            metadata={"description": "Validation messages associated with the field."},
        ),
        metadata={
            "description": "Field-level validation errors keyed by attribute name.",
        },
    )


class Api(_BaseApi):
    """エラースキーマと ``/api/overview`` を備えた flask-smorest ``Api``."""

    ERROR_SCHEMA = ErrorSchema

    # ------------------------------------------------------------------
    # OpenAPI overview（エンドポイント一覧の HTML テーブル）
    # ------------------------------------------------------------------
    def render_openapi_overview(self):
        """OpenAPI operations を一覧するインタラクティブな HTML を返す。"""

        spec_dict = self.spec.to_dict()
        components = spec_dict.get("components", {})
        security_schemes = components.get("securitySchemes", {})
        global_security = spec_dict.get("security")

        http_methods = {
            "get",
            "put",
            "post",
            "delete",
            "options",
            "head",
            "patch",
            "trace",
        }

        try:
            swagger_ui_url = flask.url_for(
                f"{self._make_doc_blueprint_name()}.openapi_swagger_ui"
            )
        except RuntimeError:
            swagger_ui_url = None

        overview_title = (
            flask.current_app.config.get("OPENAPI_OVERVIEW_TITLE")
            or flask.current_app.config.get("API_TITLE", "API Overview")
        )

        def extend_unique(values, new_items):
            for item in new_items:
                if item and item not in values:
                    values.append(item)

        def resolve_ref(ref):
            target = spec_dict
            if not isinstance(ref, str) or not ref.startswith("#/"):
                return {}
            for segment in ref[2:].split("/"):
                if not isinstance(target, dict):
                    return {}
                target = target.get(segment)
                if target is None:
                    return {}
            if isinstance(target, dict):
                return target
            return {}

        def collect_property_names(schema, visited_refs=None):
            if visited_refs is None:
                visited_refs = set()

            if not isinstance(schema, dict):
                return []

            if "$ref" in schema:
                ref = schema["$ref"]
                if ref in visited_refs:
                    return []
                visited_refs.add(ref)
                resolved = resolve_ref(ref)
                names = collect_property_names(resolved, visited_refs)
                visited_refs.remove(ref)
                return names

            names = []
            for combinator in ("allOf", "oneOf", "anyOf"):
                for sub_schema in schema.get(combinator, []) or []:
                    extend_unique(names, collect_property_names(sub_schema, visited_refs))

            properties = schema.get("properties", {})
            if isinstance(properties, dict):
                for prop_name, prop_schema in properties.items():
                    extend_unique(names, [prop_name])
                    extend_unique(names, collect_property_names(prop_schema, visited_refs))

            if schema.get("type") == "array":
                extend_unique(
                    names, collect_property_names(schema.get("items", {}), visited_refs)
                )

            return names

        def parameter_label(parameter):
            name = parameter.get("name")
            location = parameter.get("in")
            if name and location:
                return f"{name} ({location})"
            return name or ""

        def classify_security_scheme(scheme_name):
            scheme = security_schemes.get(scheme_name, {})
            scheme_type = (scheme.get("type") or "").lower()
            if scheme_type == "http":
                http_scheme = (scheme.get("scheme") or "").lower()
                if http_scheme == "bearer":
                    return "bearer"
                if http_scheme == "basic":
                    return "basic"
                return http_scheme or "http"
            if scheme_type == "apikey":
                return "apikey"
            if scheme_type == "oauth2":
                return "oauth2"
            if scheme_type == "openidconnect":
                return "openid"
            if scheme_name:
                return scheme_name
            return "unknown"

        entries = []
        scope_options = []

        for path, path_item in (spec_dict.get("paths", {}) or {}).items():
            if not isinstance(path_item, dict):
                continue

            path_parameters = [
                param
                for param in path_item.get("parameters", [])
                if isinstance(param, dict)
            ]

            for method, operation in path_item.items():
                method_lower = method.lower() if isinstance(method, str) else ""
                if method_lower not in http_methods:
                    continue
                if not isinstance(operation, dict):
                    continue

                parameters = []
                seen_params = set()

                for param in path_parameters + list(operation.get("parameters", [])):
                    if not isinstance(param, dict):
                        continue
                    key = (param.get("name"), param.get("in"))
                    if key in seen_params:
                        continue
                    seen_params.add(key)
                    label = parameter_label(param)
                    if label:
                        parameters.append(label)

                request_body = operation.get("requestBody", {})
                body_fields = []
                if isinstance(request_body, dict):
                    for media in (request_body.get("content") or {}).values():
                        if not isinstance(media, dict):
                            continue
                        schema = media.get("schema", {})
                        extend_unique(body_fields, collect_property_names(schema))
                if body_fields and parameters:
                    extend_unique(parameters, body_fields)
                elif body_fields:
                    parameters = body_fields

                summary = operation.get("summary")
                description = operation.get("description")
                if summary and description:
                    description_text = f"{summary} — {description}"
                else:
                    description_text = summary or description or ""

                operation_security = operation.get("security")
                if operation_security is None:
                    operation_security = global_security

                auth_categories = []
                scopes_for_entry = []

                if not operation_security:
                    auth_categories = ["none"]
                else:
                    for requirement in operation_security:
                        if not requirement:
                            extend_unique(auth_categories, ["none"])
                            continue
                        for scheme_name, scheme_scopes in requirement.items():
                            extend_unique(
                                auth_categories, [classify_security_scheme(scheme_name)]
                            )
                            if isinstance(scheme_scopes, list):
                                extend_unique(scopes_for_entry, scheme_scopes)

                extend_unique(scope_options, scopes_for_entry)

                tags = operation.get("tags") or []
                operation_id = operation.get("operationId")
                swagger_link = None
                if swagger_ui_url:
                    if operation_id and tags:
                        swagger_link = f"{swagger_ui_url}#/{tags[0]}/{operation_id}"
                    else:
                        swagger_link = swagger_ui_url

                entries.append(
                    {
                        "path": path,
                        "method": method_lower.upper(),
                        "args": ", ".join(parameters),
                        "scopes": " ".join(scopes_for_entry),
                        "description": description_text,
                        "auth": auth_categories or ["unknown"],
                        "link": swagger_link,
                    }
                )

        entries.sort(key=lambda item: (item["path"], item["method"]))

        auth_icons = {
            "bearer": "🔑",
            "basic": "🧾",
            "apikey": "🔏",
            "oauth2": "🔐",
            "openid": "🆔",
            "http": "🌐",
            "none": "🚫",
            "unknown": "❓",
        }

        template_context = {
            "api_entries": entries,
            "auth_icons": auth_icons,
            "overview_title": overview_title,
            "scope_options": sorted(scope_options),
            "swagger_ui_url": swagger_ui_url,
        }

        return flask.render_template("openapi_overview.html", **template_context)


__all__ = ["Api", "ErrorSchema"]

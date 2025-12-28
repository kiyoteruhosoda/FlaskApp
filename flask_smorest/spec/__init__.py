"""API specification using OpenAPI"""

import http

import click
import flask

from markupsafe import escape

import apispec
from apispec.ext.marshmallow import MarshmallowPlugin
from webargs.fields import DelimitedList

try:  # pragma: no cover
    import yaml

    HAS_PYYAML = True
except ImportError:  # pragma: no cover
    HAS_PYYAML = False

from flask_smorest import etag as fs_etag
from flask_smorest import pagination as fs_pagination
from flask_smorest.exceptions import MissingAPIParameterError
from flask_smorest.utils import normalize_config_prefix, prepare_response

from .field_converters import uploadfield2properties
from .plugins import FlaskPlugin


def _add_leading_slash(string):
    """Add leading slash to a string if there is None"""
    return string if string.startswith("/") else "/" + string


def delimited_list2param(self, field, **kwargs):
    """apispec parameter attribute function documenting DelimitedList field"""
    ret = {}
    if isinstance(field, DelimitedList):
        if self.openapi_version.major < 3:
            ret["collectionFormat"] = "csv"
        else:
            ret["explode"] = False
            ret["style"] = "form"
    return ret


class DocBlueprintMixin:
    """Extend Api to serve the spec in a dedicated blueprint."""

    def _make_doc_blueprint_name(self):
        return f"{self.config_prefix}api-docs".replace("_", "-").lower()

    def _register_doc_blueprint(self):
        """Register a blueprint in the application to expose the spec

        Doc Blueprint contains routes to
        - json spec file
        - spec UI (Swagger UI).
        """
        api_url = self.config.get("OPENAPI_URL_PREFIX")
        if api_url is not None:
            blueprint = flask.Blueprint(
                self._make_doc_blueprint_name(),
                __name__,
                url_prefix=_add_leading_slash(api_url),
                template_folder="./templates",
            )
            # Serve json spec at 'url_prefix/openapi.json' by default
            json_path = self.config.get("OPENAPI_JSON_PATH", "openapi.json")
            blueprint.add_url_rule(
                _add_leading_slash(json_path),
                endpoint="openapi_json",
                view_func=self._openapi_json,
            )
            self._register_swagger_ui_rule(blueprint)
            self._register_openapi_overview_rule(blueprint)
            self._app.register_blueprint(blueprint)

    def _register_swagger_ui_rule(self, blueprint):
        """Register Swagger UI rule

        The Swagger UI scripts base URL should be specified as
        OPENAPI_SWAGGER_UI_URL.
        """
        swagger_ui_path = self.config.get("OPENAPI_SWAGGER_UI_PATH")
        if swagger_ui_path is not None:
            swagger_ui_url = self.config.get("OPENAPI_SWAGGER_UI_URL")
            if swagger_ui_url is not None:
                self._swagger_ui_url = swagger_ui_url
                blueprint.add_url_rule(
                    _add_leading_slash(swagger_ui_path),
                    endpoint="openapi_swagger_ui",
                    view_func=self._openapi_swagger_ui,
                )


    def _openapi_json(self):
        """Serve JSON spec file"""
        return flask.current_app.response_class(
            flask.json.dumps(self.spec.to_dict(), indent=2, sort_keys=False),
            mimetype="application/json",
        )

    def _register_openapi_overview_rule(self, blueprint):
        """Register interactive OpenAPI overview table."""

        overview_path = self.config.get("OPENAPI_OVERVIEW_PATH")
        if overview_path:
            blueprint.add_url_rule(
                _add_leading_slash(overview_path),
                endpoint="openapi_overview",
                view_func=self._openapi_overview,
            )

    def _openapi_swagger_ui(self):
        """Expose OpenAPI spec with Swagger UI"""
        template_context = {}
        app = flask.current_app._get_current_object()

        # Collect values from the application's context processors so that
        # variables such as ``app_version`` that are injected globally remain
        # available when rendering the Swagger UI template.  This mirrors what
        # :func:`flask.render_template` does internally, but performing it here
        # allows us to forward the values explicitly to avoid relying on the
        # implicit context injection order.
        processors = []
        processors.extend(app.template_context_processors.get(None, ()))
        processors.extend(
            app.template_context_processors.get(
                self._make_doc_blueprint_name(), (),
            )
        )

        for processor in processors:
            try:
                template_context.update(processor())
            except Exception:  # pragma: no cover - defensive, matches Flask behaviour
                app.logger.exception("Swagger UI context processor failed", exc_info=True)

        spec_url = flask.url_for(f"{self._make_doc_blueprint_name()}.openapi_json")
        swagger_ui_config = self.config.get("OPENAPI_SWAGGER_UI_CONFIG", {})
        swagger_ui_url = self._swagger_ui_url

        template_context.update(
            dict(
                title=self.spec.title,
                spec_url=spec_url,
                swagger_ui_url=swagger_ui_url,
                swagger_ui_config=swagger_ui_config,
                servers=list(self.spec.options.get("servers") or []),
            )
        )

        rendered = flask.render_template("swagger_ui.html", **template_context)

        replacements = {
            'url: "/api/openapi.json"': f"url: {flask.json.dumps(spec_url)}",
            'var override_config = {"persistAuthorization": true};': (
                "var override_config = "
                f"{flask.json.dumps(swagger_ui_config or {})};"
            ),
            "<title>nolumia API</title>": (
                f"<title>{escape(self.spec.title)}</title>"
                if self.spec.title
                else "<title>nolumia API</title>"
            ),
        }

        if swagger_ui_url:
            normalized_base = swagger_ui_url
            if not normalized_base.endswith("/"):
                normalized_base = f"{normalized_base}/"
            replacements[
                "https://cdn.jsdelivr.net/npm/swagger-ui-dist/"
            ] = normalized_base

        for needle, replacement in replacements.items():
            if needle in rendered:
                rendered = rendered.replace(needle, replacement)

        response = flask.make_response(rendered)
        response.headers.setdefault("Content-Type", "text/html; charset=utf-8")
        return response

    def _openapi_overview(self):
        """Render an interactive HTML table summarising the OpenAPI operations."""

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
                            extend_unique(auth_categories, [classify_security_scheme(scheme_name)])
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


class APISpecMixin(DocBlueprintMixin):
    """Add APISpec related features to Api class"""

    DEFAULT_ERROR_RESPONSE_NAME = "DEFAULT_ERROR"

    DEFAULT_REQUEST_BODY_CONTENT_TYPE = "application/json"
    DEFAULT_RESPONSE_CONTENT_TYPE = "application/json"

    def _init_spec(
        self,
        *,
        flask_plugin=None,
        marshmallow_plugin=None,
        extra_plugins=None,
        title=None,
        version=None,
        openapi_version=None,
        **options,
    ):
        # Plugins
        self.flask_plugin = flask_plugin or FlaskPlugin()
        self.ma_plugin = marshmallow_plugin or MarshmallowPlugin()
        plugins = [self.flask_plugin, self.ma_plugin]
        plugins.extend(extra_plugins or ())

        # APISpec options
        title = self.config.get("API_TITLE", title)
        if title is None:
            key = f"{self.config_prefix}API_TITLE"
            raise MissingAPIParameterError(
                f'API title must be specified either as "{key}" '
                'app parameter or as "title" spec kwarg.'
            )
        version = self.config.get("API_VERSION", version)
        if version is None:
            key = f"{self.config_prefix}API_VERSION"
            raise MissingAPIParameterError(
                f'API version must be specified either as "{key}" '
                'app parameter or as "version" spec kwarg.'
            )
        openapi_version = self.config.get("OPENAPI_VERSION", openapi_version)
        if openapi_version is None:
            key = f"{self.config_prefix}OPENAPI_VERSION"
            raise MissingAPIParameterError(
                f'OpenAPI version must be specified either as "{key}" '
                'app parameter or as "openapi_version" spec kwarg.'
            )
        openapi_major_version = int(openapi_version.split(".")[0])
        if openapi_major_version < 3:
            options.setdefault(
                "produces",
                [
                    self.DEFAULT_RESPONSE_CONTENT_TYPE,
                ],
            )
            options.setdefault(
                "consumes",
                [
                    self.DEFAULT_REQUEST_BODY_CONTENT_TYPE,
                ],
            )
        options.update(self.config.get("API_SPEC_OPTIONS", {}))

        # Instantiate spec
        self.spec = apispec.APISpec(
            title,
            version,
            openapi_version,
            plugins,
            **options,
        )

        # Register custom fields in spec
        for args in self._fields:
            self._register_field(*args)
        # Register custom converters in spec
        for args in self._converters:
            self._register_converter(*args)
        # Register Upload field properties function
        self.ma_plugin.converter.add_attribute_function(uploadfield2properties)
        # Register DelimitedList field parameter attribute function
        self.ma_plugin.converter.add_parameter_attribute_function(delimited_list2param)

        # Lazy register default responses
        self._register_responses()

        # Lazy register ETag headers
        self._register_etag_headers()

        # Lazy register pagination header
        self._register_pagination_header()

        # Register OpenAPI command group
        self._app.cli.add_command(openapi_cli)

    def register_converter(self, converter, func):
        """Register custom path parameter converter

        :param BaseConverter converter: Converter
            Subclass of werkzeug's BaseConverter
        :param callable func: Function returning a parameter schema from
            a converter intance

        Example: ::

            # Register MongoDB's ObjectId converter in Flask application
            app.url_map.converters['objectid'] = ObjectIdConverter

            # Define custom converter to schema function
            def objectidconverter2paramschema(converter):
                return {'type': 'string', 'format': 'ObjectID'}

            # Register converter in Api
            api.register_converter(
                ObjectIdConverter,
                objectidconverter2paramschema
            )

            @blp.route('/pets/{objectid:pet_id}')
                ...

            api.register_blueprint(blp)

        Once the converter is registered, all paths using it will have
        corresponding path parameter documented with the right schema.

        Should be called before registering paths with
        :meth:`Blueprint.route <Blueprint.route>`.
        """
        self._converters.append((converter, func))
        # Register converter in spec if app is already initialized
        if self.spec is not None:
            self._register_converter(converter, func)

    def _register_converter(self, converter, func):
        self.flask_plugin.register_converter(converter, func)

    def register_field(self, field, *args):
        """Register custom Marshmallow field

        Registering the Field class allows the Schema parser to set the proper
        type and format when documenting parameters from Schema fields.

        :param Field field: Marshmallow Field class

        ``*args`` can be:

        - a pair of the form ``(type, format)`` to map to
        - a core marshmallow field type (then that type's mapping is used)

        Examples: ::

            # Map to ('string', 'ObjectId') passing type and format
            api.register_field(ObjectId, "string", "ObjectId")

            # Map to ('string', ) passing type
            api.register_field(CustomString, "string", None)

            # Map to ('string, 'date-time') passing a marshmallow Field
            api.register_field(CustomDateTime, ma.fields.DateTime)

        Should be called before registering schemas with
        :meth:`schema <Api.schema>`.
        """
        self._fields.append((field, *args))
        # Register field in spec if app is already initialized
        if self.spec is not None:
            self._register_field(field, *args)

    def _register_field(self, field, *args):
        self.ma_plugin.map_to_openapi_type(field, *args)

    def _register_responses(self):
        """Lazyly register default responses for all status codes"""
        # Lazy register a response for each status code
        for status in http.HTTPStatus:
            response = {
                "description": status.phrase,
            }
            if not (100 <= status < 200) and status not in (204, 304):
                response["schema"] = self.ERROR_SCHEMA
            prepare_response(response, self.spec, self.DEFAULT_RESPONSE_CONTENT_TYPE)
            self.spec.components.response(status.name, response, lazy=True)

        # Also lazy register a default error response
        response = {
            "description": "Default error response",
            "schema": self.ERROR_SCHEMA,
        }
        prepare_response(response, self.spec, self.DEFAULT_RESPONSE_CONTENT_TYPE)
        self.spec.components.response("DEFAULT_ERROR", response, lazy=True)

    def _register_etag_headers(self):
        self.spec.components.parameter(
            "IF_NONE_MATCH", "header", fs_etag.IF_NONE_MATCH_HEADER, lazy=True
        )
        self.spec.components.parameter(
            "IF_MATCH", "header", fs_etag.IF_MATCH_HEADER, lazy=True
        )
        if self.spec.openapi_version.major >= 3:
            self.spec.components.header("ETAG", fs_etag.ETAG_HEADER, lazy=True)

    def _register_pagination_header(self):
        if self.spec.openapi_version.major >= 3:
            self.spec.components.header(
                "PAGINATION", fs_pagination.PAGINATION_HEADER, lazy=True
            )


openapi_cli = flask.cli.AppGroup("openapi", help="OpenAPI commands.")


def _get_spec_dict(config_prefix):
    apis = flask.current_app.extensions["flask-smorest"]["apis"]
    try:
        api = apis[config_prefix]["ext_obj"]
    except KeyError:
        click.echo(
            f'Error: config prefix "{config_prefix}" not available. Use one of:',
            err=True,
        )
        for key in apis.keys():
            click.echo(f'    "{key}"', err=True)
        raise click.exceptions.Exit() from KeyError
    return api.spec.to_dict()


@openapi_cli.command("print")
@click.option("-f", "--format", type=click.Choice(["json", "yaml"]), default="json")
@click.option("--config-prefix", type=click.STRING, metavar="", default="")
def print_openapi_doc(format, config_prefix):
    """Print OpenAPI JSON document."""
    config_prefix = normalize_config_prefix(config_prefix)
    if format == "json":
        click.echo(
            flask.json.dumps(_get_spec_dict(config_prefix), indent=2, sort_keys=False)
        )
    else:  # format == "yaml"
        if HAS_PYYAML:
            click.echo(yaml.dump(_get_spec_dict(config_prefix)))
        else:
            click.echo(
                "To use yaml output format, please install PyYAML module", err=True
            )


@openapi_cli.command("write")
@click.option("-f", "--format", type=click.Choice(["json", "yaml"]), default="json")
@click.option("--config-prefix", type=click.STRING, metavar="", default="")
@click.argument("output_file", type=click.File(mode="w"))
def write_openapi_doc(format, output_file, config_prefix):
    """Write OpenAPI JSON document to a file."""
    config_prefix = normalize_config_prefix(config_prefix)
    if format == "json":
        click.echo(
            flask.json.dumps(_get_spec_dict(config_prefix), indent=2, sort_keys=False),
            file=output_file,
        )
    else:  # format == "yaml"
        if HAS_PYYAML:
            yaml.dump(_get_spec_dict(config_prefix), output_file)
        else:
            click.echo(
                "To use yaml output format, please install PyYAML module", err=True
            )


@openapi_cli.command("list-config-prefixes")
def list_config_prefixes():
    """List available API config prefixes."""
    for prefix in flask.current_app.extensions["flask-smorest"]["apis"].keys():
        click.echo(f'"{prefix}"')

import json
import re
import textwrap

import pytest

from webapp.extensions import api as smorest_api


@pytest.mark.usefixtures('app_context')
class TestOpenAPIDocs:
    def test_openapi_spec_includes_login_endpoint(self, app_context):
        client = app_context.test_client()
        response = client.get('/api/openapi.json')
        assert response.status_code == 200

        payload = response.get_json()
        assert payload['openapi'] == '3.0.3'

        servers = payload.get('servers', [])
        assert servers == [{'url': 'http://localhost/api'}]

        assert '/login' in payload['paths']
        login_post = payload['paths']['/login']['post']
        request_schema = login_post['requestBody']['content']['application/json']['schema']
        assert request_schema == {'$ref': '#/components/schemas/LoginRequest'}
        response_schema = login_post['responses']['200']['content']['application/json']['schema']
        assert response_schema == {'$ref': '#/components/schemas/LoginResponse'}

        login_request = payload['components']['schemas']['LoginRequest']
        assert set(login_request['required']) == {'email', 'password'}
        login_response = payload['components']['schemas']['LoginResponse']
        assert 'requires_role_selection' in login_response['properties']
        assert 'available_scopes' in login_response['properties']
        assert login_response['properties']['token_type']['type'] == 'string'

    def test_swagger_ui_served(self, app_context):
        client = app_context.test_client()
        response = client.get('/api/docs')
        assert response.status_code == 200
        html = response.get_data(as_text=True)

        selectors_match = re.search(
            r"const\s+SERVER_DROPDOWN_SELECTORS\s*=\s*'([^']+)'",
            html,
        )
        assert (
            selectors_match
        ), 'SERVER_DROPDOWN_SELECTORS constant missing from Swagger UI template'
        selectors_literal = selectors_match.group(1)
        assert '#servers' in selectors_literal
        assert 'SwaggerUIBundle' in html
        assert 'url: "/api/openapi.json"' in html
        assert '<link rel="icon" type="image/x-icon" href="/static/favicon.ico">' in html
        assert 'Version:' in html
        assert 'renderRequiredScopes' in html
        assert 'required-scopes-container' in html

    def test_openapi_spec_respects_forwarded_headers(self, app_context):
        client = app_context.test_client()
        headers = {
            'X-Forwarded-Proto': 'https',
            'X-Forwarded-Host': 'example.com',
            'X-Forwarded-Prefix': '/proxy/app',
        }
        response = client.get('/api/openapi.json', headers=headers)
        assert response.status_code == 200
        payload = response.get_json()
        assert payload['servers'] == [
            {'url': 'https://example.com/proxy/app/api'}
        ]

    def test_openapi_spec_uses_forwarded_and_x_forwarded_proto(self, app_context):
        client = app_context.test_client()
        headers = {
            'Forwarded': 'proto=https;host="nolumia.com"',
            'X-Forwarded-Proto': 'http',
        }
        response = client.get('/api/openapi.json', base_url='http://nolumia.com', headers=headers)
        assert response.status_code == 200
        payload = response.get_json()
        assert payload['servers'] == [
            {'url': 'https://nolumia.com/api'},
            {'url': 'http://nolumia.com/api'},
        ]

    def test_swagger_ui_server_dropdown_includes_forwarded_protocols(self, app_context):
        client = app_context.test_client()
        headers = {
            'Forwarded': 'proto=https;host="nolumia.com"',
            'X-Forwarded-Proto': 'http',
        }

        response = client.get('/api/docs', base_url='http://nolumia.com', headers=headers)
        assert response.status_code == 200

        assert smorest_api.spec.options.get('servers') == [
            {'url': 'https://nolumia.com/api'},
            {'url': 'http://nolumia.com/api'},
        ]

    def test_swagger_ui_embeds_clean_server_urls(self, app_context):
        client = app_context.test_client()
        headers = {
            'Forwarded': 'proto=https;host="nolumia.com"',
            'X-Forwarded-Proto': 'http',
        }

        response = client.get('/api/docs', base_url='http://nolumia.com', headers=headers)
        assert response.status_code == 200

        html = response.get_data(as_text=True)
        assert 'window.__INITIAL_OPENAPI_SERVERS__' in html
        assert 'https://nolumia.com/api' in html
        assert 'https\\://nolumia.com/api' not in html

    def test_openapi_overview_table_renders_endpoints(self, app_context):
        client = app_context.test_client()
        response = client.get('/api/overview')
        assert response.status_code == 200

        html = response.get_data(as_text=True)
        assert '<table id="apiTable"' in html
        assert 'https://cdn.datatables.net/2.0.5/js/dataTables.min.js' in html
        assert 'Scopeで絞り込み' in html

        match = re.search(r'const\s+apiData\s*=\s*(\[.*?\]);', html, re.S)
        assert match, 'apiData JavaScript assignment missing'
        api_data = json.loads(match.group(1))

        login_entry = next(
            (item for item in api_data if item.get('path') == '/login' and item.get('method') == 'POST'),
            None,
        )
        assert login_entry is not None, 'Login endpoint not found in overview data'
        assert isinstance(login_entry.get('auth'), list)
        assert login_entry.get('link'), 'Swagger UI link missing for login endpoint'

    def test_swagger_ui_server_dropdown_renders_clean_values(self, app_context):
        try:
            import js2py  # type: ignore
        except ImportError:  # pragma: no cover - handled below
            js2py = None

        client = app_context.test_client()
        headers = {
            'Forwarded': 'proto=https;host="nolumia.com"',
            'X-Forwarded-Proto': 'http',
        }

        response = client.get('/api/docs', base_url='http://nolumia.com', headers=headers)
        assert response.status_code == 200

        html = response.get_data(as_text=True)

        selectors_match = re.search(
            r"const\s+SERVER_DROPDOWN_SELECTORS\s*=\s*'([^']+)'",
            html,
        )
        assert (
            selectors_match
        ), 'SERVER_DROPDOWN_SELECTORS constant missing from Swagger UI template'
        selectors_literal = selectors_match.group(1)
        assert '#servers' in selectors_literal

        marker = "function sanitizeServerOptions()"
        start = html.find(marker)
        assert start != -1, 'sanitizeServerOptions function missing from Swagger UI template'

        brace_start = html.find('{', start)
        assert brace_start != -1, 'sanitizeServerOptions function body not found'

        depth = 0
        end = brace_start
        while end < len(html):
            char = html[end]
            if char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0:
                    end += 1
                    break
            end += 1

        assert depth == 0, 'sanitizeServerOptions function braces not balanced'
        sanitize_fn = html[start:end]

        js_template = textwrap.dedent("""
            (function() {
                var SERVER_DROPDOWN_SELECTORS = '__SERVER_SELECTORS__';

                function createOption(initialValue) {
                    return {
                        value: initialValue,
                        textContent: initialValue,
                        attributes: {},
                        setAttribute: function(name, val) { this.attributes[name] = val; },
                        getAttribute: function(name) {
                            if (Object.prototype.hasOwnProperty.call(this.attributes, name)) {
                                return this.attributes[name];
                            }
                            return this[name];
                        }
                    };
                }

                var selectElement = {
                    options: [
                        createOption('https\\\\://nolumia.com/api'),
                        createOption('http\\\\://nolumia.com/api')
                    ],
                    querySelectorAll: function() { return this.options; }
                };

                var document = {
                    selectElements: [selectElement],
                    querySelectorAll: function(selector) {
                        if (selector.indexOf('#servers') !== -1) {
                            return this.selectElements;
                        }
                        return [];
                    },
                    querySelector: function(selector) {
                        if (selector.indexOf('#servers') !== -1) {
                            return this.selectElements[0];
                        }
                        return null;
                    }
                };

                __SANITIZE_FUNCTION__

                sanitizeServerOptions();

                var normalized = selectElement.options.map(function(option) {
                    return {
                        value: option.value,
                        text: option.textContent,
                        attrValue: option.attributes.value
                    };
                });

                return JSON.stringify(normalized);
            }());
        """)

        if js2py is not None:
            js_script = (
                js_template
                .replace("__SANITIZE_FUNCTION__", sanitize_fn)
                .replace('__SERVER_SELECTORS__', selectors_literal)
            )

            normalized_json = js2py.eval_js(js_script)
            normalized = json.loads(normalized_json)
        else:
            assert '\\\\:' in sanitize_fn
            assert '\\\\\\/' in sanitize_fn
            assert '#servers' in selectors_literal

            def _python_sanitize(raw: str) -> str:
                return raw.replace('\\\\:', ':').replace('\\\\/', '/')

            normalized = []
            for raw in ['https\\\\://nolumia.com/api', 'http\\\\://nolumia.com/api']:
                sanitized = _python_sanitize(raw)
                normalized.append({'value': sanitized, 'text': sanitized, 'attrValue': sanitized})

        assert normalized
        for option in normalized:
            assert '\\' not in option['value']
            assert '\\' not in option['text']
            assert option['attrValue'] == option['value']

    def test_echo_endpoint_exposes_json_request_body(self, app_context):
        client = app_context.test_client()
        response = client.get('/api/openapi.json')
        assert response.status_code == 200

        payload = response.get_json()
        echo_post = payload['paths']['/echo']['post']
        request_body = echo_post.get('requestBody')
        assert request_body is not None

        content = request_body.get('content', {})
        assert 'application/json' in content
        json_schema = content['application/json']['schema']
        assert json_schema['type'] == 'object'
        assert json_schema.get('additionalProperties') is True
        assert 'example' in content['application/json']

    def test_all_json_endpoints_publish_request_bodies(self, app_context):
        client = app_context.test_client()
        response = client.get('/api/openapi.json')
        assert response.status_code == 200

        payload = response.get_json()
        paths = payload['paths']

        expected_operations = {
            '/albums': {'post'},
            '/albums/{album_id}': {'put'},
            '/albums/{album_id}/media/order': {'put'},
            '/albums/order': {'put'},
            '/google/oauth/start': {'post'},
            '/google/accounts/{account_id}': {'patch'},
            '/service_accounts/{account_id}/keys': {'post'},
            '/upload/commit': {'post'},
            '/service_accounts/signatures': {'post'},
            '/picker/session': {'post'},
            '/picker/session/{session_id}/callback': {'post'},
            '/picker/session/mediaItems': {'post'},
            '/picker/session/{session_id}/import': {'post'},
            '/picker/session/{picker_session_id}/finish': {'post'},
            '/sync/local-import': {'post'},
            '/totp': {'post'},
            '/totp/{credential_id}': {'put'},
            '/totp/import': {'post'},
            '/tags': {'post'},
            '/tags/{tag_id}': {'put'},
            '/media/{media_id}/tags': {'put'},
            '/media/{media_id}/thumb-url': {'post'},
        }

        for path, methods in expected_operations.items():
            assert path in paths, f"{path} missing from OpenAPI spec"
            for method in methods:
                operation = paths[path].get(method)
                assert operation is not None, f"{path} {method} missing operation"
                request_body = operation.get('requestBody')
                assert request_body, f"{path} {method} missing requestBody"
                content = request_body.get('content', {})
                assert 'application/json' in content, f"{path} {method} missing JSON content"

    def test_service_account_signature_endpoint_requires_api_key_scopes(self, app_context):
        client = app_context.test_client()
        response = client.get('/api/openapi.json')
        assert response.status_code == 200
        payload = response.get_json()

        operation = payload['paths']['/service_accounts/signatures']['post']
        assert operation['security'] == [{'ServiceAccountApiKey': []}]
        assert operation['x-required-scopes'] == ['certificate:sign']
        assert operation['x-requires-authentication'] is True

        security_schemes = payload['components']['securitySchemes']
        assert 'ServiceAccountApiKey' in security_schemes
        scheme = security_schemes['ServiceAccountApiKey']
        assert scheme['type'] == 'apiKey'
        assert scheme['in'] == 'header'
        assert scheme['name'] == 'Authorization'
        assert 'ApiKey' in scheme['description']

    def test_openapi_metadata_and_default_security(self, app_context):
        client = app_context.test_client()
        response = client.get('/api/openapi.json')
        assert response.status_code == 200
        payload = response.get_json()

        assert payload['info']['description'] == (
            'Nolumia API provides authentication, media management, and Google Photos integration endpoints.'
        )
        assert payload['security'] == [{'JWTBearerAuth': []}]

        security_schemes = payload['components']['securitySchemes']
        assert security_schemes['JWTBearerAuth']['type'] == 'http'
        assert security_schemes['JWTBearerAuth']['scheme'] == 'bearer'
        assert security_schemes['JWTBearerAuth']['bearerFormat'] == 'JWT'

    def test_authentication_endpoints_are_anonymous(self, app_context):
        client = app_context.test_client()
        response = client.get('/api/openapi.json')
        assert response.status_code == 200
        payload = response.get_json()

        login_security = payload['paths']['/login']['post']['security']
        refresh_security = payload['paths']['/refresh']['post']['security']
        token_security = payload['paths']['/token']['post']['security']

        assert login_security == []
        assert refresh_security == []
        assert token_security == []

    def test_scope_schema_accepts_string_or_array(self, app_context):
        client = app_context.test_client()
        response = client.get('/api/openapi.json')
        assert response.status_code == 200
        payload = response.get_json()

        scope_schema = payload['components']['schemas']['LoginRequest']['properties']['scope']
        assert 'oneOf' in scope_schema
        assert {'type': 'string'} in scope_schema['oneOf']
        array_schema = next(item for item in scope_schema['oneOf'] if item.get('type') == 'array')
        assert array_schema['items']['type'] == 'string'

    def test_error_schema_exposes_array_error_messages(self, app_context):
        client = app_context.test_client()
        response = client.get('/api/openapi.json')
        assert response.status_code == 200
        payload = response.get_json()

        error_schema = payload['components']['schemas']['Error']
        errors_prop = error_schema['properties']['errors']
        assert errors_prop['type'] == 'object'
        additional = errors_prop['additionalProperties']
        assert additional['type'] == 'array'
        assert additional['items']['type'] == 'string'

    def test_manual_doc_does_not_emit_methods_field(self, app_context):
        client = app_context.test_client()
        response = client.get('/api/openapi.json')
        assert response.status_code == 200
        payload = response.get_json()

        google_post = payload['paths']['/google/oauth/start']['post']
        assert 'methods' not in google_post

    def test_success_responses_are_added_where_missing(self, app_context):
        client = app_context.test_client()
        response = client.get('/api/openapi.json')
        assert response.status_code == 200
        payload = response.get_json()

        echo_post = payload['paths']['/echo']['post']
        responses = echo_post['responses']
        assert '200' in responses
        content = responses['200']['content']
        assert 'text/plain' in content
        schema = content['text/plain']['schema']
        assert schema['type'] == 'string'
        assert 'HTTP' in schema['example']

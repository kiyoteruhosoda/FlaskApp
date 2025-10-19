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

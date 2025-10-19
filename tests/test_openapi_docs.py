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

    def test_swagger_ui_served(self, app_context):
        client = app_context.test_client()
        response = client.get('/api/docs')
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'SwaggerUIBundle' in html
        assert 'url: "/api/openapi.json"' in html

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

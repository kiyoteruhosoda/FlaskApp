import pytest


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

        assert '/api/login' in payload['paths']
        login_post = payload['paths']['/api/login']['post']
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

    def test_echo_endpoint_exposes_json_request_body(self, app_context):
        client = app_context.test_client()
        response = client.get('/api/openapi.json')
        assert response.status_code == 200

        payload = response.get_json()
        echo_post = payload['paths']['/api/echo']['post']
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
            '/api/albums': {'post'},
            '/api/albums/{album_id}': {'put'},
            '/api/albums/{album_id}/media/order': {'put'},
            '/api/albums/order': {'put'},
            '/api/google/oauth/start': {'post'},
            '/api/google/accounts/{account_id}': {'patch'},
            '/api/service_accounts/{account_id}/keys': {'post'},
            '/api/upload/commit': {'post'},
            '/api/service_accounts/signatures': {'post'},
            '/api/picker/session': {'post'},
            '/api/picker/session/{session_id}/callback': {'post'},
            '/api/picker/session/mediaItems': {'post'},
            '/api/picker/session/{session_id}/import': {'post'},
            '/api/picker/session/{picker_session_id}/finish': {'post'},
            '/api/sync/local-import': {'post'},
            '/api/totp': {'post'},
            '/api/totp/{credential_id}': {'put'},
            '/api/totp/import': {'post'},
            '/api/tags': {'post'},
            '/api/tags/{tag_id}': {'put'},
            '/api/media/{media_id}/tags': {'put'},
            '/api/media/{media_id}/thumb-url': {'post'},
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

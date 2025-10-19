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

    def test_openapi_spec_ignores_untrusted_forwarded_entries(self, app_context):
        client = app_context.test_client()
        headers = {
            'Forwarded': (
                'proto=https;host="evil.example", '
                'proto=https;host="trusted.example"'
            )
        }
        response = client.get('/api/openapi.json', headers=headers)
        assert response.status_code == 200
        payload = response.get_json()
        assert payload['servers'] == [
            {'url': 'https://trusted.example/api'},
            {'url': 'http://localhost/api'},
        ]

    def test_openapi_spec_limits_x_forwarded_host_to_trusted_entries(self, app_context):
        client = app_context.test_client()
        headers = {
            'X-Forwarded-Host': 'evil.example, trusted.example',
            'X-Forwarded-Proto': 'https',
        }
        response = client.get('/api/openapi.json', headers=headers)
        assert response.status_code == 200
        payload = response.get_json()
        assert payload['servers'] == [
            {'url': 'https://trusted.example/api'},
            {'url': 'http://localhost/api'},
        ]

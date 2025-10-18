import pytest

from webapp.api.openapi import openapi_spec


@pytest.mark.usefixtures('app_context')
class TestOpenAPIDocs:
    def test_openapi_spec_includes_login_endpoint(self, app_context):
        client = app_context.test_client()
        response = client.get('/api/openapi.json')
        assert response.status_code == 200

        payload = response.get_json()
        assert payload['openapi'] == '3.0.3'

        login_path = payload['paths']['/login']
        login_post = login_path['post']
        assert login_post['summary'] == 'ユーザー認証してJWTを発行'
        assert login_post['operationId'].endswith('_post')
        assert login_post['responses']['200']['description']
        servers = [server['url'] for server in payload['servers']]
        assert servers[0] == 'http://localhost/api'

    def test_openapi_spec_respects_forwarded_proto(self, app_context):
        client = app_context.test_client()
        response = client.get(
            '/api/openapi.json',
            headers={
                'X-Forwarded-Proto': 'https',
                'X-Forwarded-Host': 'nolumia.com',
            },
        )
        assert response.status_code == 200

        payload = response.get_json()
        servers = [server['url'] for server in payload['servers']]
        assert servers[0] == 'https://nolumia.com/api'

    def test_openapi_spec_uses_forwarded_header_for_external_https(self, app_context):
        client = app_context.test_client()
        response = client.get(
            '/api/openapi.json',
            headers={
                'Forwarded': 'proto=https;host="nolumia.com"',
                'X-Forwarded-Proto': 'http',
                'Host': 'nolumia.com',
            },
        )
        assert response.status_code == 200

        payload = response.get_json()
        servers = [server['url'] for server in payload['servers']]
        assert servers[0] == 'https://nolumia.com/api'
        assert 'http://nolumia.com/api' in servers

    def test_openapi_spec_avoids_duplicate_script_root_in_forwarded_prefix(self, app_context):
        with app_context.test_request_context(
            '/api/openapi.json',
            headers={'X-Forwarded-Prefix': '/proxy/app'},
            base_url='http://localhost/app',
        ):
            payload = openapi_spec().get_json()
        assert payload['servers'][0]['url'] == 'http://localhost/proxy/app/api'

    def test_openapi_spec_appends_missing_script_root(self, app_context):
        with app_context.test_request_context(
            '/api/openapi.json',
            headers={'X-Forwarded-Prefix': '/proxy'},
            base_url='http://localhost/app',
        ):
            payload = openapi_spec().get_json()
        assert payload['servers'][0]['url'] == 'http://localhost/proxy/app/api'

    def test_openapi_spec_handles_absolute_forwarded_prefix(self, app_context):
        with app_context.test_request_context(
            '/api/openapi.json',
            headers={
                'X-Forwarded-Proto': 'https',
                'X-Forwarded-Host': 'nolumia.com',
                'X-Forwarded-Prefix': 'https://nolumia.com/api',
            },
        ):
            payload = openapi_spec().get_json()
        servers = [server['url'] for server in payload['servers']]
        assert servers[0] == 'https://nolumia.com/api'

    def test_swagger_ui_served(self, app_context):
        client = app_context.test_client()
        response = client.get('/api/docs')
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'SwaggerUIBundle' in html
        assert '/api/openapi.json' in html

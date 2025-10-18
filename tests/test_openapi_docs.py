import pytest


@pytest.mark.usefixtures('app_context')
class TestOpenAPIDocs:
    def test_openapi_spec_includes_login_endpoint(self, app_context):
        client = app_context.test_client()
        response = client.get('/api/openapi.json')
        assert response.status_code == 200

        payload = response.get_json()
        assert payload['openapi'] == '3.0.3'

        login_path = payload['paths']['/api/login']
        login_post = login_path['post']
        assert login_post['summary'] == 'ユーザー認証してJWTを発行'
        assert login_post['operationId'].endswith('_post')
        assert login_post['responses']['200']['description']
        assert payload['servers'][0]['url'] == 'http://localhost'

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
        assert payload['servers'][0]['url'] == 'https://nolumia.com'

    def test_openapi_spec_preserves_script_root_without_forwarded_prefix(self, app_context):
        client = app_context.test_client()
        response = client.get(
            '/api/openapi.json',
            environ_overrides={'SCRIPT_NAME': '/app'},
        )

        assert response.status_code == 200

        payload = response.get_json()
        assert payload['servers'][0]['url'] == 'http://localhost/app'

    def test_openapi_spec_deduplicates_forwarded_prefix_and_script_root(self, app_context):
        client = app_context.test_client()
        response = client.get(
            '/api/openapi.json',
            headers={
                'X-Forwarded-Proto': 'https',
                'X-Forwarded-Host': 'nolumia.com',
                'X-Forwarded-Prefix': '/app',
            },
            environ_overrides={'SCRIPT_NAME': '/app'},
        )

        assert response.status_code == 200

        payload = response.get_json()
        assert payload['servers'][0]['url'] == 'https://nolumia.com/app'

    def test_swagger_ui_served(self, app_context):
        client = app_context.test_client()
        response = client.get('/api/docs')
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'SwaggerUIBundle' in html
        assert '/api/openapi.json' in html

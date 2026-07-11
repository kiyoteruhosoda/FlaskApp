import { test, expect } from '@playwright/test';
import { setupAuth } from './helpers';

const MOCK_CONFIG = {
  status: 'success',
  application_sections: [
    {
      identifier: 'security',
      label: 'Security & Signing',
      description: 'Secrets and signing settings.',
      anchor_id: 'section-security',
      search_text: 'security secret webauthn',
      fields: [
        {
          key: 'WEBAUTHN_RP_ID',
          label: 'WebAuthn relying party ID',
          data_type: 'string',
          required: true,
          description: 'Domain name asserted during WebAuthn.',
          current_json: '"localhost"',
          default_json: '"localhost"',
          form_value: 'localhost',
          choices: [],
          multiline: false,
          using_default: false,
          allow_empty: false,
          allow_null: false,
          editable: true,
          default_hint: null,
          search_text: 'webauthn_rp_id webauthn relying party id localhost',
          section: 'security',
          section_label: 'Security & Signing',
          anchor_id: 'setting-WEBAUTHN_RP_ID',
        },
      ],
    },
    {
      identifier: 'mail',
      label: 'Mail Configuration',
      description: 'Email server settings.',
      anchor_id: 'section-mail',
      search_text: 'mail email smtp',
      fields: [
        {
          key: 'MAIL_ENABLED',
          label: 'Enable mail functionality',
          data_type: 'boolean',
          required: true,
          description: 'Enable or disable email sending.',
          current_json: 'false',
          default_json: 'false',
          form_value: 'false',
          choices: [['true', 'True'], ['false', 'False']],
          multiline: false,
          using_default: true,
          allow_empty: false,
          allow_null: false,
          editable: true,
          default_hint: null,
          search_text: 'mail_enabled enable mail functionality',
          section: 'mail',
          section_label: 'Mail Configuration',
          anchor_id: 'setting-MAIL_ENABLED',
        },
        {
          key: 'MAIL_PORT',
          label: 'SMTP port',
          data_type: 'integer',
          required: true,
          description: 'SMTP server port number.',
          current_json: '587',
          default_json: '587',
          form_value: '587',
          choices: [],
          multiline: false,
          using_default: true,
          allow_empty: false,
          allow_null: false,
          editable: true,
          default_hint: 'Common ports: 587 (TLS), 465 (SSL)',
          search_text: 'mail_port smtp port',
          section: 'mail',
          section_label: 'Mail Configuration',
          anchor_id: 'setting-MAIL_PORT',
        },
      ],
    },
  ],
  application_fields: [
    {
      key: 'WEBAUTHN_RP_ID', label: 'WebAuthn relying party ID', data_type: 'string', required: true,
      description: '', current_json: '"localhost"', default_json: '"localhost"', form_value: 'localhost',
      choices: [], multiline: false, using_default: false, allow_empty: false, allow_null: false,
      editable: true, default_hint: null, search_text: '', section: 'security', section_label: 'Security & Signing', anchor_id: 'setting-WEBAUTHN_RP_ID',
    },
    {
      key: 'MAIL_ENABLED', label: 'Enable mail functionality', data_type: 'boolean', required: true,
      description: '', current_json: 'false', default_json: 'false', form_value: 'false',
      choices: [['true', 'True'], ['false', 'False']], multiline: false, using_default: true, allow_empty: false, allow_null: false,
      editable: true, default_hint: null, search_text: '', section: 'mail', section_label: 'Mail Configuration', anchor_id: 'setting-MAIL_ENABLED',
    },
    {
      key: 'MAIL_PORT', label: 'SMTP port', data_type: 'integer', required: true,
      description: '', current_json: '587', default_json: '587', form_value: '587',
      choices: [], multiline: false, using_default: true, allow_empty: false, allow_null: false,
      editable: true, default_hint: null, search_text: '', section: 'mail', section_label: 'Mail Configuration', anchor_id: 'setting-MAIL_PORT',
    },
  ],
  cors_fields: [
    {
      key: 'allowedOrigins', label: 'Allowed origins', data_type: 'list', required: false,
      description: '', current_json: '["https://example.com"]', default_json: '[]', form_value: 'https://example.com',
      choices: [], multiline: true, using_default: false, allow_empty: true, allow_null: false,
      editable: true, default_hint: null, search_text: '', section: 'cors', section_label: 'CORS', anchor_id: 'setting-allowedOrigins',
    },
  ],
  cors_effective_origins: ['https://example.com'],
  signing_setting: { mode: 'builtin', kid: null, group_code: null },
  signingGroups: [
    { groupCode: 'grp1', groupLabel: 'Signing Group 1', latestCertificate: { kid: 'kid1', issuedAt: null, expiresAt: null, algorithm: 'RS256', subject: 'CN=test' } },
  ],
  builtin_signing_secret: 'existing-secret',
  timestamps: { application_config_updated_at: null, cors_config_updated_at: null, signing_config_updated_at: null },
  descriptions: { application_config_description: null, cors_config_description: null },
};

const routeConfig = async (page: any) => {
  await page.route(
    (url: URL) => url.pathname === '/api/admin/config',
    (route: any) => route.fulfill({ json: MOCK_CONFIG })
  );
};

test.describe('Config Page', () => {
  test('shows sections and fields', async ({ page }) => {
    await setupAuth(page);
    await routeConfig(page);

    await page.goto('/admin/config');
    await expect(page.getByTestId('config-page')).toBeVisible();
    await expect(page.getByTestId('config-section-security')).toBeVisible();
    await expect(page.getByTestId('config-section-mail')).toBeVisible();
    await expect(page.getByTestId('config-field-WEBAUTHN_RP_ID')).toBeVisible();
    await expect(page.getByTestId('config-field-MAIL_ENABLED')).toBeVisible();
  });

  test('shows forbidden message on 403', async ({ page }) => {
    await setupAuth(page);
    await page.route(
      (url) => url.pathname === '/api/admin/config',
      (route) => route.fulfill({ status: 403, json: { detail: { error: 'forbidden' } } })
    );

    await page.goto('/admin/config');
    await expect(page.getByText('You do not have permission to view this page')).toBeVisible();
  });

  test('filters fields by search', async ({ page }) => {
    await setupAuth(page);
    await routeConfig(page);

    await page.goto('/admin/config');
    await page.fill('[data-testid="config-search"]', 'mail');
    await expect(page.getByTestId('config-section-mail')).toBeVisible();
    await expect(page.getByTestId('config-section-security')).not.toBeVisible();
  });

  test('shows no results message', async ({ page }) => {
    await setupAuth(page);
    await routeConfig(page);

    await page.goto('/admin/config');
    await page.fill('[data-testid="config-search"]', 'zzzznomatch');
    await expect(page.getByTestId('config-no-results')).toBeVisible();
  });

  test('shows save bar when a field is modified', async ({ page }) => {
    await setupAuth(page);
    await routeConfig(page);

    await page.goto('/admin/config');
    await page.fill('[data-testid="config-field-MAIL_PORT"]', '465');
    await expect(page.getByTestId('config-save-bar')).toBeVisible();
    await expect(page.getByTestId('config-modified-MAIL_PORT')).toBeVisible();
  });

  test('saves modified application setting', async ({ page }) => {
    await setupAuth(page);
    await routeConfig(page);
    let putBody: any = null;
    await page.route(
      (url) => url.pathname === '/api/admin/config' && true,
      async (route) => {
        if (route.request().method() === 'PUT') {
          putBody = route.request().postDataJSON();
          await route.fulfill({ json: { ...MOCK_CONFIG, updated: true } });
        } else {
          await route.fulfill({ json: MOCK_CONFIG });
        }
      }
    );

    await page.goto('/admin/config');
    await page.fill('[data-testid="config-field-MAIL_PORT"]', '465');
    await page.getByTestId('config-save').click();
    await expect(page.getByTestId('config-success')).toBeVisible();
    expect(putBody.updates.MAIL_PORT).toBe('465');
  });

  test('toggles boolean switch and discards', async ({ page }) => {
    await setupAuth(page);
    await routeConfig(page);

    await page.goto('/admin/config');
    await page.getByTestId('config-field-MAIL_ENABLED').check();
    await expect(page.getByTestId('config-save-bar')).toBeVisible();
    await page.getByTestId('config-discard').click();
    await expect(page.getByTestId('config-save-bar')).not.toBeVisible();
  });

  test('saves CORS origins', async ({ page }) => {
    await setupAuth(page);
    await routeConfig(page);
    await page.route(
      (url) => url.pathname === '/api/admin/config/cors',
      (route) => route.fulfill({ json: { ...MOCK_CONFIG, updated: true } })
    );

    await page.goto('/admin/config');
    await page.fill('[data-testid="config-cors-origins"]', 'https://new.example.com');
    await page.getByTestId('config-cors-save').click();
    await expect(page.getByTestId('config-success')).toBeVisible();
  });

  test('shows signing options', async ({ page }) => {
    await setupAuth(page);
    await routeConfig(page);

    await page.goto('/admin/config');
    await expect(page.getByTestId('config-signing-builtin')).toBeVisible();
    await expect(page.getByTestId('config-signing-secret')).toBeVisible();
    await page.getByTestId('config-signing-server').check();
    await expect(page.getByTestId('config-signing-group')).toBeVisible();
  });

  test('saves signing setting', async ({ page }) => {
    await setupAuth(page);
    await routeConfig(page);
    await page.route(
      (url) => url.pathname === '/api/admin/config/signing',
      (route) => route.fulfill({ json: { ...MOCK_CONFIG, updated: true } })
    );

    await page.goto('/admin/config');
    await page.fill('[data-testid="config-signing-secret"]', 'a-new-secret');
    await page.getByTestId('config-signing-save').click();
    await expect(page.getByTestId('config-success')).toBeVisible();
  });
});

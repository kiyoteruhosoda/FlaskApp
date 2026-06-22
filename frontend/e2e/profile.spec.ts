import { test, expect } from '@playwright/test';
import { setupAuth, TEST_USER } from './helpers';

const TOTP_SETUP = {
  secret: 'BASE32SECRET',
  otpauth_uri: 'otpauth://totp/PhotoNest:admin@example.com?secret=BASE32SECRET',
  qr_data_uri: 'data:image/png;base64,iVBORw0KGgo=',
};

const MOCK_PASSKEYS = [
  { id: 1, name: 'Touch ID', createdAt: '2024-01-01T00:00:00Z', lastUsedAt: '2024-06-01T00:00:00Z', transports: ['internal'] },
];

function mockProfileRoutes(page: Parameters<typeof page.route>[1] extends never ? never : import('@playwright/test').Page) {
  return Promise.all([
    page.route((url) => url.pathname === '/api/auth/2fa/status', (route) => route.fulfill({ json: { enabled: false } })),
    page.route((url) => url.pathname === '/api/auth/passkeys', (route) => route.fulfill({ json: { passkeys: [] } })),
  ]);
}

test.describe('Profile', () => {
  test('shows user info', async ({ page }) => {
    await setupAuth(page);
    await mockProfileRoutes(page);

    await page.goto('/profile');
    await expect(page.getByTestId('profile-page')).toBeVisible();
    await expect(page.getByText(TEST_USER.email)).toBeVisible();
  });

  test('enters and cancels edit mode', async ({ page }) => {
    await setupAuth(page);
    await mockProfileRoutes(page);

    await page.goto('/profile');
    await page.getByTestId('profile-edit-btn').click();
    await expect(page.locator('input[name="email"]')).toBeVisible();
    await page.getByTestId('profile-cancel-btn').click();
    await expect(page.locator('input[name="email"]')).not.toBeVisible();
  });

  test('saves profile changes', async ({ page }) => {
    await setupAuth(page);
    await mockProfileRoutes(page);
    await page.route(
      (url) => url.pathname === '/api/auth/profile',
      (route) => route.fulfill({ json: { updated: true, user: { id: 1, email: 'updated@example.com', username: 'admin' } } })
    );

    await page.goto('/profile');
    await page.getByTestId('profile-edit-btn').click();
    await page.fill('input[name="email"]', 'updated@example.com');
    await page.getByTestId('profile-save-btn').click();

    // Save round-trip completes and the view returns to read-only mode
    await expect(page.locator('input[name="email"]')).not.toBeVisible();
    await expect(page.getByTestId('profile-edit-btn')).toBeVisible();
  });

  test('shows 2FA disabled status', async ({ page }) => {
    await setupAuth(page);
    await mockProfileRoutes(page);

    await page.goto('/profile');
    await expect(page.getByText('2段階認証 無効')).toBeVisible();
    await expect(page.getByTestId('totp-enable-btn')).toBeVisible();
  });

  test('shows 2FA enabled status', async ({ page }) => {
    await setupAuth(page);
    await page.route((url) => url.pathname === '/api/auth/2fa/status', (route) => route.fulfill({ json: { enabled: true } }));
    await page.route((url) => url.pathname === '/api/auth/passkeys', (route) => route.fulfill({ json: { passkeys: [] } }));

    await page.goto('/profile');
    await expect(page.getByText('2段階認証 有効')).toBeVisible();
    await expect(page.getByTestId('totp-disable-btn')).toBeVisible();
  });

  test('enables 2FA', async ({ page }) => {
    await setupAuth(page);
    await mockProfileRoutes(page);
    await page.route(
      (url) => url.pathname === '/api/auth/2fa/setup',
      (route) => route.fulfill({ json: TOTP_SETUP })
    );
    await page.route(
      (url) => url.pathname === '/api/auth/2fa/confirm',
      (route) => route.fulfill({ json: { enabled: true } })
    );

    await page.goto('/profile');
    await page.getByTestId('totp-enable-btn').click();

    // QR code and secret are shown
    await expect(page.getByText('QRコード')).toBeVisible();
    await expect(page.getByText('BASE32SECRET')).toBeVisible();

    // Enter 6-digit code and verify
    await page.fill('input[name="totp_code"]', '123456');
    await page.getByTestId('totp-verify-btn').click();

    await expect(page.getByText('2段階認証を有効にしました')).toBeVisible();
    await expect(page.getByText('2段階認証 有効')).toBeVisible();
  });

  test('disables 2FA', async ({ page }) => {
    await setupAuth(page);
    await page.route((url) => url.pathname === '/api/auth/2fa/status', (route) => route.fulfill({ json: { enabled: true } }));
    await page.route((url) => url.pathname === '/api/auth/passkeys', (route) => route.fulfill({ json: { passkeys: [] } }));
    await page.route(
      (url) => url.pathname === '/api/auth/2fa',
      (route) => route.fulfill({ json: { enabled: false } })
    );

    await page.goto('/profile');
    await page.getByTestId('totp-disable-btn').click();
    await expect(page.getByTestId('totp-disable-confirm')).toBeVisible();
    await page.getByTestId('totp-disable-confirm-btn').click();

    await expect(page.getByText('2段階認証を無効にしました')).toBeVisible();
    await expect(page.getByText('2段階認証 無効')).toBeVisible();
  });

  test('shows passkeys section with empty state', async ({ page }) => {
    await setupAuth(page);
    await mockProfileRoutes(page);

    await page.goto('/profile');
    await expect(page.getByTestId('passkeys-section')).toBeVisible();
    await expect(page.getByTestId('passkeys-empty')).toBeVisible();
  });

  test('shows registered passkeys', async ({ page }) => {
    await setupAuth(page);
    await page.route((url) => url.pathname === '/api/auth/2fa/status', (route) => route.fulfill({ json: { enabled: false } }));
    await page.route((url) => url.pathname === '/api/auth/passkeys', (route) => route.fulfill({ json: { passkeys: MOCK_PASSKEYS } }));

    await page.goto('/profile');
    await expect(page.getByTestId('passkeys-list')).toBeVisible();
    await expect(page.getByText('Touch ID')).toBeVisible();
  });

  test('deletes a passkey', async ({ page }) => {
    await setupAuth(page);
    await page.route((url) => url.pathname === '/api/auth/2fa/status', (route) => route.fulfill({ json: { enabled: false } }));
    await page.route((url) => url.pathname === '/api/auth/passkeys', (route) => route.fulfill({ json: { passkeys: MOCK_PASSKEYS } }));
    await page.route(
      (url) => url.pathname === '/api/auth/passkeys/1',
      (route) => route.fulfill({ json: { result: 'deleted' } })
    );

    await page.goto('/profile');
    await expect(page.getByTestId('passkey-item')).toBeVisible();
    await page.getByTestId('passkey-delete-btn').click();
    await expect(page.getByTestId('passkeys-empty')).toBeVisible();
  });
});

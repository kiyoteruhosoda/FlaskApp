import { test, expect } from '@playwright/test';
import { TEST_USER } from './helpers';

const TOKENS = { access_token: 'acc', refresh_token: 'ref' };

test.describe('Login', () => {
  test('password login navigates to app', async ({ page }) => {
    await page.route(
      (url) => url.pathname === '/api/auth/login',
      (route) => route.fulfill({ json: { ...TOKENS, requires_role_selection: false } })
    );
    await page.route(
      (url) => url.pathname === '/api/auth/me',
      (route) => route.fulfill({ json: TEST_USER })
    );

    await page.goto('/login');
    await expect(page.getByTestId('login-page')).toBeVisible();
    await page.fill('input[name="email"]', 'admin@example.com');
    await page.fill('input[name="password"]', 'secret');
    await page.getByTestId('login-submit').click();

    await expect(page).toHaveURL(/\/dashboard$/);
  });

  test('shows TOTP field when required, then logs in', async ({ page }) => {
    let attempt = 0;
    await page.route(
      (url) => url.pathname === '/api/auth/login',
      (route) => {
        attempt += 1;
        if (attempt === 1) {
          route.fulfill({ status: 401, json: { detail: { error: 'totp_required' } } });
        } else {
          route.fulfill({ json: { ...TOKENS, requires_role_selection: false } });
        }
      }
    );
    await page.route(
      (url) => url.pathname === '/api/auth/me',
      (route) => route.fulfill({ json: TEST_USER })
    );

    await page.goto('/login');
    await page.fill('input[name="email"]', 'admin@example.com');
    await page.fill('input[name="password"]', 'secret');
    await page.getByTestId('login-submit').click();

    // TOTP 入力欄が出現
    await expect(page.locator('input[name="totp_code"]')).toBeVisible();
    await page.fill('input[name="totp_code"]', '123456');
    await page.getByTestId('login-submit').click();
    await expect(page).toHaveURL(/\/dashboard$/);
  });

  test('shows error on invalid credentials', async ({ page }) => {
    await page.route(
      (url) => url.pathname === '/api/auth/login',
      (route) => route.fulfill({ status: 401, json: { detail: { error: 'invalid_credentials' } } })
    );

    await page.goto('/login');
    await page.fill('input[name="email"]', 'admin@example.com');
    await page.fill('input[name="password"]', 'bad');
    await page.getByTestId('login-submit').click();

    // 生のエラーコードではなく、利用者向けに翻訳されたメッセージが表示される
    await expect(page.getByText('Invalid email or password')).toBeVisible();
    await expect(page.getByText('invalid_credentials', { exact: true })).not.toBeVisible();
    await expect(page).toHaveURL(/\/login$/);
  });

  test('does not show raw invalid_token error code', async ({ page }) => {
    // ログイン成功直後の getCurrentUser() が一時的に失敗するケースを再現。
    // 内部エラーコードがそのまま画面に表示されないことを確認する。
    await page.route(
      (url) => url.pathname === '/api/auth/login',
      (route) => route.fulfill({ json: { ...TOKENS, requires_role_selection: false } })
    );
    await page.route(
      (url) => url.pathname === '/api/auth/me',
      (route) => route.fulfill({ status: 401, json: { detail: { error: 'invalid_token' } } })
    );

    await page.goto('/login');
    await page.fill('input[name="email"]', 'admin@example.com');
    await page.fill('input[name="password"]', 'secret');
    await page.getByTestId('login-submit').click();

    await expect(page.getByText('invalid_token', { exact: true })).not.toBeVisible();
  });

  test('passkey login navigates to app', async ({ page }) => {
    // navigator.credentials.get と PublicKeyCredential をスタブ
    await page.addInitScript(() => {
      // @ts-ignore
      window.PublicKeyCredential = function () {};
      Object.defineProperty(navigator, 'credentials', {
        configurable: true,
        value: {
          get: async () => ({
            id: 'cred-1',
            type: 'public-key',
            rawId: new Uint8Array([1, 2, 3]).buffer,
            response: {
              clientDataJSON: new Uint8Array([4]).buffer,
              authenticatorData: new Uint8Array([5]).buffer,
              signature: new Uint8Array([6]).buffer,
              userHandle: null,
            },
          }),
        },
      });
    });

    await page.route(
      (url) => url.pathname === '/auth/passkey/options/login',
      (route) => route.fulfill({ json: { challenge: 'AAAA', allowCredentials: [] } })
    );
    let verified = false;
    await page.route(
      (url) => url.pathname === '/auth/passkey/verify/login',
      (route) => {
        verified = true;
        route.fulfill({ json: { ...TOKENS, requires_role_selection: false } });
      }
    );
    await page.route(
      (url) => url.pathname === '/api/auth/me',
      (route) => route.fulfill({ json: TEST_USER })
    );

    await page.goto('/login');
    await page.getByTestId('passkey-login-btn').click();
    await expect(page).toHaveURL(/\/dashboard$/);
    expect(verified).toBe(true);
  });
});

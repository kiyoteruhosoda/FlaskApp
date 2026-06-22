import { Page } from '@playwright/test';

export const TEST_USER = {
  id: 1,
  username: 'admin',
  display_name: 'Admin',
  email: 'admin@example.com',
  permissions: ['media:view', 'media:session', 'album:view', 'admin:system-settings'],
  roles: [{ id: 1, name: 'admin' }],
};

/**
 * 認証済み状態をセットアップする。
 * localStorage にトークンを入れて初期 isAuthenticated=true にし、/auth/me をモック。
 */
export async function setupAuth(page: Page): Promise<void> {
  await page.addInitScript(() => {
    localStorage.setItem('access_token', 'e2e-test-token');
  });
  await page.route(
    (url) => url.pathname === '/api/auth/me',
    (route) => route.fulfill({ json: TEST_USER })
  );
  await page.route(
    (url) => url.pathname === '/api/auth/roles',
    (route) => route.fulfill({ json: { roles: TEST_USER.roles } })
  );
}

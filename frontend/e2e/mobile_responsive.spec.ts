import { test, expect, Page } from '@playwright/test';
import { setupAuth } from './helpers';

// スマホ幅 (iPhone SE 相当) で「管理系ではない」画面に横スクロールが
// 発生しないことを機械的に検証する。横スクロールは固定幅要素やはみ出す
// テーブル・カード等、モバイル未対応のレイアウト崩れの最も分かりやすい兆候。
const MOBILE_VIEWPORT = { width: 375, height: 667 };

async function expectNoHorizontalOverflow(page: Page) {
  const { scrollWidth, clientWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  // サブピクセル誤差を許容して 1px までは許容する
  expect(scrollWidth, 'horizontal overflow detected (scrollWidth > clientWidth)').toBeLessThanOrEqual(
    clientWidth + 1
  );
}

test.describe('Mobile responsiveness (non-admin pages)', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize(MOBILE_VIEWPORT);
  });

  test('login page', async ({ page }) => {
    await page.goto('/login');
    await expect(page.getByTestId('login-page')).toBeVisible();
    await expectNoHorizontalOverflow(page);
  });

  test('register page', async ({ page }) => {
    await page.goto('/register');
    await expect(page.getByTestId('register-page')).toBeVisible();
    await expectNoHorizontalOverflow(page);
  });

  test('forgot password page', async ({ page }) => {
    await page.goto('/forgot-password');
    await expectNoHorizontalOverflow(page);
  });

  test.describe('authenticated shell', () => {
    test.beforeEach(async ({ page }) => {
      await setupAuth(page);
    });

    test('home', async ({ page }) => {
      await page.goto('/');
      await expectNoHorizontalOverflow(page);
    });

    test('dashboard', async ({ page }) => {
      await page.goto('/dashboard');
      await expectNoHorizontalOverflow(page);
    });

    test('profile', async ({ page }) => {
      await page.route((url) => url.pathname === '/api/auth/2fa/status', (route) => route.fulfill({ json: { enabled: false } }));
      await page.route((url) => url.pathname === '/api/auth/passkeys', (route) => route.fulfill({ json: { passkeys: [] } }));
      await page.goto('/profile');
      await expect(page.getByTestId('profile-page')).toBeVisible();
      await expectNoHorizontalOverflow(page);
    });

    test('media gallery', async ({ page }) => {
      await page.route(
        (url) => url.pathname === '/api/media',
        (route) => route.fulfill({ json: { items: [], hasNext: false } })
      );
      await page.goto('/media');
      await expect(page.getByTestId('media-empty')).toBeVisible();
      await expectNoHorizontalOverflow(page);
    });

    test('albums', async ({ page }) => {
      await page.route(
        (url) => url.pathname === '/api/albums',
        (route) => route.fulfill({ json: { items: [], hasNext: false } })
      );
      await page.goto('/albums');
      await expect(page.getByTestId('albums-page')).toBeVisible();
      await expectNoHorizontalOverflow(page);
    });

    test('tags', async ({ page }) => {
      await page.route(
        (url) => url.pathname === '/api/tags',
        (route) => route.fulfill({ json: { items: [] } })
      );
      await page.goto('/tags');
      await expect(page.getByTestId('tags-page')).toBeVisible();
      await expectNoHorizontalOverflow(page);
    });

    test('media duplicates', async ({ page }) => {
      await page.route(
        (url) => url.pathname === '/api/media/duplicates',
        (route) => route.fulfill({ json: { groups: [] } })
      );
      await page.goto('/media/duplicates');
      await expectNoHorizontalOverflow(page);
    });

    test('sessions', async ({ page }) => {
      await page.route(
        (url) => url.pathname === '/api/picker/sessions',
        (route) =>
          route.fulfill({
            json: {
              sessions: [],
              pagination: { hasNext: false, hasPrev: false, nextCursor: null, prevCursor: null, currentPage: 1, totalPages: 1, totalCount: 0 },
              server_time: '2026-06-21T12:00:00Z',
            },
          })
      );
      await page.goto('/sessions');
      await expect(page.getByTestId('sessions-empty')).toBeVisible();
      await expectNoHorizontalOverflow(page);
    });

    test('jobs', async ({ page }) => {
      await page.route(
        (url) => url.pathname === '/api/sync/jobs',
        (route) =>
          route.fulfill({
            json: {
              jobs: [],
              pagination: { currentPage: 1, pageSize: 50, totalCount: 0, totalPages: 1, hasNext: false, hasPrev: false },
              filter: { status: null, target: null, since: null, until: null },
              server_time: '2026-06-21T12:00:00Z',
            },
          })
      );
      await page.goto('/jobs');
      await expectNoHorizontalOverflow(page);
    });

    test('photo imports', async ({ page }) => {
      await page.route(
        (url) => url.pathname === '/api/sync/local-import/status',
        (route) =>
          route.fulfill({
            json: {
              config: {
                import_dir: '/data/import',
                originals_dir: '/data/originals',
                import_dir_absolute: '/data/import',
                import_dir_realpath: '/data/import',
                import_dir_exists: true,
                originals_dir_exists: true,
              },
              status: { pending_files: 0, ready: true },
              directories: [],
              defaults: { duplicateRegeneration: 'regenerate' },
              server_time: '2024-06-01T10:00:00Z',
            },
          })
      );
      await page.goto('/photo-imports');
      await expect(page.getByTestId('photo-imports-page')).toBeVisible();
      await expectNoHorizontalOverflow(page);
    });

    test('photo settings', async ({ page }) => {
      await page.route(
        (url) => url.pathname === '/api/sync/local-import/status',
        (route) =>
          route.fulfill({
            json: {
              config: {
                import_dir: '/data/import',
                originals_dir: '/data/originals',
                import_dir_absolute: '/data/import',
                import_dir_realpath: '/data/import',
                import_dir_exists: true,
                originals_dir_exists: true,
              },
              status: { pending_files: 0, ready: true },
              directories: [
                { key: 'import', config_key: 'MEDIA_LOCAL_IMPORT_DIRECTORY', label: 'Import directory', path: '/data/import', absolute: '/data/import', realpath: '/data/import', exists: true, source: 'configured' },
              ],
              defaults: { duplicateRegeneration: 'regenerate' },
              server_time: '2024-06-01T10:00:00Z',
            },
          })
      );
      await page.goto('/photo-settings');
      await expect(page.getByTestId('photo-settings-page')).toBeVisible();
      await expectNoHorizontalOverflow(page);
    });

    test('wiki index', async ({ page }) => {
      await page.route(
        (url) => url.pathname === '/wiki/api/index',
        (route) =>
          route.fulfill({
            json: { recentPages: [], popularPages: [], categories: [], totalPages: 0 },
          })
      );
      await page.goto('/wiki');
      await expectNoHorizontalOverflow(page);
    });

    test('mobile sidebar opens as an overlay drawer', async ({ page }) => {
      await page.goto('/dashboard');
      // モバイルではサイドバーは既定で非表示
      await expect(page.getByText('Sync Jobs')).not.toBeVisible();
      await page.getByRole('button', { name: 'Toggle navigation' }).first().click();
      await expect(page.getByText('Sync Jobs')).toBeVisible();
      await expectNoHorizontalOverflow(page);
    });
  });
});

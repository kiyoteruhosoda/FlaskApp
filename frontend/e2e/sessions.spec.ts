import { test, expect } from '@playwright/test';
import { setupAuth } from './helpers';

function sessionRow(overrides: Record<string, any> = {}) {
  return {
    id: 1,
    sessionId: 'local_import_abc123',
    accountId: null,
    status: 'imported',
    selectedCount: 5,
    createdAt: '2026-06-21T09:00:00Z',
    lastProgressAt: '2026-06-21T09:05:00Z',
    counts: { imported: 5 },
    accountEmail: null,
    isLocalImport: true,
    ...overrides,
  };
}

function listResponse(sessions: any[]) {
  return {
    sessions,
    pagination: {
      hasNext: false,
      hasPrev: false,
      nextCursor: null,
      prevCursor: null,
      currentPage: 1,
      totalPages: 1,
      totalCount: sessions.length,
    },
    server_time: '2026-06-21T12:00:00Z',
  };
}

test.describe('Import Sessions page', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
  });

  test('renders session list with status and type', async ({ page }) => {
    await page.route(
      (url) => url.pathname === '/api/picker/sessions',
      (route) =>
        route.fulfill({
          json: listResponse([
            sessionRow({ id: 1, status: 'imported', isLocalImport: true }),
            sessionRow({
              id: 2,
              sessionId: 'picker_xyz',
              status: 'error',
              isLocalImport: false,
              accountEmail: 'user@example.com',
              counts: { failed: 2 },
            }),
          ]),
        })
    );

    await page.goto('/sessions');
    await expect(page.getByTestId('sessions-page')).toBeVisible();
    await expect(page.getByTestId('session-row')).toHaveCount(2);
    await expect(page.getByTestId('session-status').first()).toHaveText('imported');
    // 詳細リンクは React のセッション詳細ページを指す
    await expect(page.getByTestId('session-detail-link').first()).toHaveAttribute(
      'href',
      /\/sessions\//
    );
  });

  test('shows empty state', async ({ page }) => {
    await page.route(
      (url) => url.pathname === '/api/picker/sessions',
      (route) => route.fulfill({ json: listResponse([]) })
    );
    await page.goto('/sessions');
    await expect(page.getByTestId('sessions-empty')).toBeVisible();
  });
});

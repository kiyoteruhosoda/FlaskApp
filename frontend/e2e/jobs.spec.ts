import { test, expect } from '@playwright/test';
import { setupAuth } from './helpers';

function job(overrides: Record<string, any> = {}) {
  return {
    id: 1,
    target: 'local_import_task',
    targetCategory: 'local_import',
    taskName: 'local_import_task',
    queueName: null,
    trigger: 'manual',
    status: 'success',
    accountId: null,
    sessionId: 1,
    celeryTaskId: null,
    startedAt: '2026-06-21T10:00:00Z',
    finishedAt: '2026-06-21T10:01:00Z',
    durationMs: 60000,
    statsSummary: { total: 10, success: 9, failed: 1 },
    errorMessage: null,
    retryable: false,
    ...overrides,
  };
}

function listResponse(jobs: any[]) {
  return {
    jobs,
    pagination: {
      currentPage: 1,
      pageSize: 50,
      totalCount: jobs.length,
      totalPages: 1,
      hasNext: false,
      hasPrev: false,
    },
    filter: { status: null, target: null, since: null, until: null },
    server_time: '2026-06-21T12:00:00Z',
  };
}

test.describe('Sync Jobs page', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
  });

  test('renders job history and filters by status', async ({ page }) => {
    const all = [
      job({ id: 1, status: 'success' }),
      job({
        id: 2,
        target: 'picker_import_item',
        targetCategory: 'picker_import',
        status: 'failed',
        finishedAt: null,
        durationMs: null,
        statsSummary: {},
        errorMessage: 'boom',
        retryable: true,
      }),
    ];

    await page.route(
      (url) => url.pathname === '/api/sync/jobs',
      (route) => {
        const status = new URL(route.request().url()).searchParams.get('status');
        const jobs = status ? all.filter((j) => j.status === status) : all;
        route.fulfill({ json: listResponse(jobs) });
      }
    );

    await page.goto('/jobs');
    await expect(page.getByTestId('jobs-page')).toBeVisible();
    await expect(page.getByTestId('job-row')).toHaveCount(2);

    // failed で絞り込み
    await page.getByTestId('filter-status').selectOption('failed');
    await expect(page.getByTestId('job-row')).toHaveCount(1);
    await expect(page.getByTestId('job-status')).toHaveText('failed');
    // 失敗ジョブには再実行ボタンが出る
    await expect(page.getByTestId('job-retry-btn')).toBeVisible();
  });

  test('opens job detail with stats', async ({ page }) => {
    await page.route(
      (url) => url.pathname === '/api/sync/jobs',
      (route) => route.fulfill({ json: listResponse([job({ id: 7 })]) })
    );
    await page.route(
      (url) => url.pathname === '/api/sync/jobs/7',
      (route) =>
        route.fulfill({
          json: {
            job: {
              ...job({ id: 7 }),
              stats: { total: 10, success: 10, details: [1, 2, 3] },
              args: { session_id: 'abc' },
            },
            server_time: '2026-06-21T12:00:00Z',
          },
        })
    );

    await page.goto('/jobs');
    await page.getByTestId('job-detail-btn').first().click();
    await expect(page.getByTestId('job-detail-stats')).toContainText('"total": 10');
    await expect(page.getByTestId('job-detail-stats')).toContainText('details');
  });

  test('shows empty state', async ({ page }) => {
    await page.route(
      (url) => url.pathname === '/api/sync/jobs',
      (route) => route.fulfill({ json: listResponse([]) })
    );
    await page.goto('/jobs');
    await expect(page.getByTestId('jobs-empty')).toBeVisible();
  });
});

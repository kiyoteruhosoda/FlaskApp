import { test, expect } from '@playwright/test';
import { setupAuth } from './helpers';

const MOCK_SESSION_STATUS = {
  id: 1,
  sessionId: 'picker_sessions/abc123',
  status: 'completed',
  accountId: null,
  accountEmail: null,
  selectedCount: 5,
  counts: { imported: 4, failed: 1 },
  createdAt: '2024-06-01T10:00:00Z',
  lastProgressAt: '2024-06-01T10:05:00Z',
  isLocalImport: true,
  stats: null,
};

const MOCK_SELECTIONS = {
  selections: [
    {
      id: 1,
      sessionDbId: 1,
      googleMediaId: null,
      filename: 'photo1.jpg',
      status: 'imported',
      attempts: 1,
      error: null,
      localFilePath: '/media/photo1.jpg',
      enqueuedAt: '2024-06-01T10:01:00Z',
      startedAt: '2024-06-01T10:01:01Z',
      finishedAt: '2024-06-01T10:01:10Z',
    },
    {
      id: 2,
      sessionDbId: 1,
      googleMediaId: null,
      filename: 'photo2.jpg',
      status: 'failed',
      attempts: 3,
      error: 'File not found on disk',
      localFilePath: null,
      enqueuedAt: '2024-06-01T10:02:00Z',
      startedAt: '2024-06-01T10:02:01Z',
      finishedAt: '2024-06-01T10:02:30Z',
    },
  ],
  pagination: { hasNext: false, totalCount: 2 },
};

const MOCK_LOGS = {
  logs: [
    { id: 1, level: 'INFO', message: 'Import started', timestamp: '2024-06-01T10:01:00Z', fileTaskId: null, progressStep: null },
    { id: 2, level: 'ERROR', message: 'File not found: photo2.jpg', timestamp: '2024-06-01T10:02:30Z', fileTaskId: null, progressStep: null },
  ],
  hasNext: false,
  nextCursor: null,
  fileTaskIds: [],
};

const MOCK_SELECTION_ERROR = {
  session: { id: 1, sessionId: 'picker_sessions/abc123', status: 'completed', accountId: null },
  selection: MOCK_SELECTIONS.selections[1],
  logs: [MOCK_LOGS.logs[1]],
};

// ===== Session Detail =====

test.describe('Session Detail Page', () => {
  const sessionId = 'picker_sessions%2Fabc123';
  const sessionIdRaw = 'picker_sessions/abc123';

  test('shows session status and selections', async ({ page }) => {
    await setupAuth(page);
    await page.route(
      (url) => url.pathname === `/api/picker/session/${sessionId}`,
      (route) => route.fulfill({ json: MOCK_SESSION_STATUS })
    );
    await page.route(
      (url) => url.pathname === `/api/picker/session/${sessionId}/selections`,
      (route) => route.fulfill({ json: MOCK_SELECTIONS })
    );
    await page.route(
      (url) => url.pathname === `/api/picker/session/${sessionId}/logs`,
      (route) => route.fulfill({ json: MOCK_LOGS })
    );

    await page.goto(`/sessions/${encodeURIComponent(sessionIdRaw)}`);
    await expect(page.getByTestId('session-detail-page')).toBeVisible();
    await expect(page.getByTestId('session-status-badge')).toBeVisible();
    await expect(page.getByText('completed')).toBeVisible();
    await expect(page.getByTestId('selection-row').first()).toBeVisible();
    await expect(page.getByText('photo1.jpg')).toBeVisible();
  });

  test('shows failed selections with error detail link', async ({ page }) => {
    await setupAuth(page);
    await page.route(
      (url) => url.pathname.startsWith('/api/picker/session/'),
      (route) => {
        const p = route.request().url();
        if (p.includes('/selections')) route.fulfill({ json: MOCK_SELECTIONS });
        else if (p.includes('/logs')) route.fulfill({ json: MOCK_LOGS });
        else route.fulfill({ json: MOCK_SESSION_STATUS });
      }
    );

    await page.goto(`/sessions/${encodeURIComponent(sessionIdRaw)}`);
    await expect(page.getByTestId('selection-error-link')).toBeVisible();
  });

  test('shows logs tab', async ({ page }) => {
    await setupAuth(page);
    await page.route(
      (url) => url.pathname.startsWith('/api/picker/session/'),
      (route) => {
        const p = route.request().url();
        if (p.includes('/selections')) route.fulfill({ json: MOCK_SELECTIONS });
        else if (p.includes('/logs')) route.fulfill({ json: MOCK_LOGS });
        else route.fulfill({ json: MOCK_SESSION_STATUS });
      }
    );

    await page.goto(`/sessions/${encodeURIComponent(sessionIdRaw)}`);
    // i18n default locale is 'ja'; the Logs tab renders as 'ログ'
    await page.getByRole('tab', { name: 'ログ' }).click();
    await expect(page.getByTestId('logs-list')).toBeVisible();
    await expect(page.getByText('Import started')).toBeVisible();
  });
});

// ===== Selection Error Detail =====

test.describe('Selection Error Detail Page', () => {
  const sessionId = 'picker_sessions/abc123';
  const selectionId = 2;

  test('shows error details', async ({ page }) => {
    await setupAuth(page);
    await page.route(
      (url) =>
        url.pathname === `/api/picker/session/${encodeURIComponent(sessionId)}/selections/${selectionId}/error`,
      (route) => route.fulfill({ json: MOCK_SELECTION_ERROR })
    );

    await page.goto(`/sessions/${encodeURIComponent(sessionId)}/selection/${selectionId}/error`);
    await expect(page.getByTestId('selection-error-page')).toBeVisible();
    await expect(page.getByTestId('error-message')).toBeVisible();
    await expect(page.getByText('File not found on disk')).toBeVisible();
  });
});

// ===== Slideshow =====

const MOCK_ALBUM_WITH_MEDIA = {
  album: {
    id: 1,
    title: 'Family Photos',
    description: null,
    visibility: 'private',
    coverImageId: null,
    coverMediaId: 1,
    mediaCount: 3,
    createdAt: '2024-01-01T00:00:00Z',
    updatedAt: '2024-01-01T00:00:00Z',
    lastModified: '2024-01-01T00:00:00Z',
    displayOrder: null,
    mediaIds: [1, 2, 3],
    media: [
      { id: 1, filename: 'photo1.jpg', shotAt: null, thumbnailUrl: '/thumb/1', fullUrl: '/full/1', sortIndex: 0, tags: [] },
      { id: 2, filename: 'photo2.jpg', shotAt: null, thumbnailUrl: '/thumb/2', fullUrl: '/full/2', sortIndex: 1, tags: [] },
      { id: 3, filename: 'photo3.jpg', shotAt: null, thumbnailUrl: '/thumb/3', fullUrl: '/full/3', sortIndex: 2, tags: [] },
    ],
  },
};

test.describe('Slideshow Page', () => {
  test('shows slideshow page', async ({ page }) => {
    await setupAuth(page);
    await page.route(
      (url) => url.pathname === '/api/albums/1',
      (route) => route.fulfill({ json: MOCK_ALBUM_WITH_MEDIA })
    );
    await page.route(
      (url) => url.pathname.startsWith('/api/media/') && url.pathname.endsWith('/thumb-url'),
      (route) => route.fulfill({ json: { url: '/thumb/1' } })
    );

    await page.goto('/albums/1/slideshow');
    await expect(page.getByTestId('slideshow-page')).toBeVisible();
    await expect(page.getByTestId('slideshow-controls')).toBeVisible();
  });

  test('shows prev/next buttons', async ({ page }) => {
    await setupAuth(page);
    await page.route(
      (url) => url.pathname === '/api/albums/1',
      (route) => route.fulfill({ json: MOCK_ALBUM_WITH_MEDIA })
    );
    await page.route(
      (url) => url.pathname.startsWith('/api/media/') && url.pathname.endsWith('/thumb-url'),
      (route) => route.fulfill({ json: { url: '/thumb/1' } })
    );

    await page.goto('/albums/1/slideshow');
    await page.mouse.move(400, 300);
    await expect(page.getByTestId('slideshow-prev')).toBeVisible();
    await expect(page.getByTestId('slideshow-next')).toBeVisible();
  });

  test('shows empty state for album with no photos', async ({ page }) => {
    await setupAuth(page);
    await page.route(
      (url) => url.pathname === '/api/albums/99',
      (route) =>
        route.fulfill({
          json: {
            album: { ...MOCK_ALBUM_WITH_MEDIA.album, id: 99, mediaCount: 0, media: [], mediaIds: [] },
          },
        })
    );

    await page.goto('/albums/99/slideshow');
    await expect(page.getByText('このアルバムに写真がありません')).toBeVisible();
  });
});

// ===== Photo Settings =====

const MOCK_LOCAL_IMPORT_STATUS = {
  config: {
    import_dir: '/data/import',
    originals_dir: '/data/originals',
    import_dir_absolute: '/data/import',
    import_dir_realpath: '/data/import',
    import_dir_exists: true,
    originals_dir_exists: true,
  },
  status: { pending_files: 12, ready: true },
  directories: [
    { key: 'import', config_key: 'MEDIA_LOCAL_IMPORT_DIRECTORY', label: 'Import directory', path: '/data/import', absolute: '/data/import', realpath: '/data/import', exists: true, source: 'configured' },
    { key: 'originals', config_key: 'MEDIA_ORIGINALS_DIRECTORY', label: 'Originals directory', path: '/data/originals', absolute: '/data/originals', realpath: '/data/originals', exists: true, source: 'configured' },
  ],
  defaults: { duplicateRegeneration: 'regenerate' },
  server_time: '2024-06-01T10:00:00Z',
};

test.describe('Photo Settings Page', () => {
  test('shows directory status', async ({ page }) => {
    await setupAuth(page);
    await page.route(
      (url) => url.pathname === '/api/sync/local-import/status',
      (route) => route.fulfill({ json: MOCK_LOCAL_IMPORT_STATUS })
    );

    await page.goto('/photo-settings');
    await expect(page.getByTestId('photo-settings-page')).toBeVisible();
    await expect(page.getByTestId('directories-table')).toBeVisible();
    await expect(page.getByText('Import directory')).toBeVisible();
  });

});

// ===== Photo Imports =====

test.describe('Photo Imports Page', () => {
  test('shows ready state and trigger button', async ({ page }) => {
    await setupAuth(page);
    await page.route(
      (url) => url.pathname === '/api/sync/local-import/status',
      (route) => route.fulfill({ json: MOCK_LOCAL_IMPORT_STATUS })
    );

    await page.goto('/photo-imports');
    await expect(page.getByTestId('photo-imports-page')).toBeVisible();
    await expect(page.getByTestId('import-ready-badge')).toBeVisible();
    await expect(page.getByTestId('trigger-import-btn')).toBeVisible();
    await expect(page.getByTestId('upload-file-input')).toBeVisible();
  });

  test('shows not ready state', async ({ page }) => {
    await setupAuth(page);
    const notReady = {
      ...MOCK_LOCAL_IMPORT_STATUS,
      status: { pending_files: 0, ready: false },
    };
    await page.route(
      (url) => url.pathname === '/api/sync/local-import/status',
      (route) => route.fulfill({ json: notReady })
    );

    await page.goto('/photo-imports');
    await expect(page.getByTestId('import-ready-badge')).toHaveText('未準備');
  });

  test('uploads files to the import directory', async ({ page }) => {
    await setupAuth(page);
    await page.route(
      (url) => url.pathname === '/api/sync/local-import/status',
      (route) => route.fulfill({ json: MOCK_LOCAL_IMPORT_STATUS })
    );
    await page.route(
      (url) => url.pathname === '/api/sync/local-import/upload',
      (route) =>
        route.fulfill({
          json: {
            success: true,
            saved: [{ filename: 'photo.jpg', size: 10 }],
            skipped: [],
            server_time: '2024-06-01T10:00:00Z',
          },
        })
    );

    await page.goto('/photo-imports');
    await page.getByTestId('upload-file-input').setInputFiles({
      name: 'photo.jpg',
      mimeType: 'image/jpeg',
      buffer: Buffer.from('fake image'),
    });
    await page.getByTestId('upload-btn').click();
    await expect(page.getByTestId('upload-result')).toBeVisible();
  });
});

// ===== Photo Exports =====

test.describe('Photo Exports Page', () => {
  test('shows placeholder page', async ({ page }) => {
    await setupAuth(page);
    await page.goto('/admin/photo-exports');
    await expect(page.getByTestId('photo-exports-page')).toBeVisible();
    await expect(page.getByText('エクスポート管理は未実装です。')).toBeVisible();
  });
});

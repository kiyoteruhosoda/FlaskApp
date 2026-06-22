import { test, expect } from '@playwright/test';
import { setupAuth } from './helpers';

// 1x1 透明 PNG の data URI（署名URLの代用。ネットワーク不要で <img> が読める）
const PNG =
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==';

function photo(overrides: Record<string, any> = {}) {
  return {
    id: 1,
    filename: 'photo1.jpg',
    shot_at: '2026-06-20T08:00:00Z',
    mime_type: 'image/jpeg',
    width: 4000,
    height: 3000,
    is_video: 0,
    has_playback: 0,
    bytes: 123456,
    source_type: 'local',
    source_label: 'Local Import',
    account_id: null,
    account_email: null,
    camera_make: 'Canon',
    camera_model: 'EOS',
    tags: [{ id: 1, name: 'Family', attr: 'person' }],
    ...overrides,
  };
}

test.describe('Media gallery', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    // すべての thumb-url リクエストに data URI を返す
    await page.route(
      (url) => /\/api\/media\/\d+\/thumb-url$/.test(url.pathname),
      (route) => route.fulfill({ json: { url: PNG } })
    );
  });

  test('renders grid and opens detail', async ({ page }) => {
    await page.route(
      (url) => url.pathname === '/api/media',
      (route) =>
        route.fulfill({
          json: {
            items: [photo({ id: 1 }), photo({ id: 2, filename: 'clip.mp4', is_video: 1 })],
            hasNext: false,
            nextCursor: null,
            server_time: 'x',
          },
        })
    );

    await page.goto('/media');
    await expect(page.getByTestId('media-page')).toBeVisible();
    await expect(page.getByTestId('media-card')).toHaveCount(2);

    await page.getByTestId('media-card').first().click();
    await expect(page.getByTestId('media-preview')).toBeVisible();
    await expect(page.getByText('Canon EOS')).toBeVisible();
    await expect(page.getByText('Family')).toBeVisible();
  });

  test('shows empty state', async ({ page }) => {
    await page.route(
      (url) => url.pathname === '/api/media',
      (route) => route.fulfill({ json: { items: [], hasNext: false } })
    );
    await page.goto('/media');
    await expect(page.getByTestId('media-empty')).toBeVisible();
  });
});

test.describe('Albums', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    await page.route(
      (url) => /\/api\/media\/\d+\/thumb-url$/.test(url.pathname),
      (route) => route.fulfill({ json: { url: PNG } })
    );
  });

  test('renders album cards with count', async ({ page }) => {
    await page.route(
      (url) => url.pathname === '/api/albums',
      (route) =>
        route.fulfill({
          json: {
            items: [
              {
                id: 1,
                title: 'Vacation',
                description: null,
                visibility: 'private',
                coverImageId: null,
                coverMediaId: null,
                mediaCount: 12,
                createdAt: null,
                updatedAt: null,
              },
            ],
            hasNext: false,
          },
        })
    );
    await page.goto('/albums');
    await expect(page.getByTestId('albums-page')).toBeVisible();
    await expect(page.getByTestId('album-card')).toHaveCount(1);
    await expect(page.getByText('Vacation')).toBeVisible();
    // 既定言語(ja)では「12 件」、en では「12 items」
    await expect(page.getByText(/12\s*(items|件)/)).toBeVisible();
  });
});

test.describe('Tags', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
  });

  test('renders tag list', async ({ page }) => {
    await page.route(
      (url) => url.pathname === '/api/tags',
      (route) =>
        route.fulfill({
          json: {
            items: [
              { id: 1, name: 'Family', attr: 'person' },
              { id: 2, name: 'Tokyo', attr: 'place' },
            ],
          },
        })
    );
    await page.goto('/tags');
    await expect(page.getByTestId('tags-page')).toBeVisible();
    await expect(page.getByTestId('tag-item')).toHaveCount(2);
    await expect(page.getByText('Tokyo')).toBeVisible();
  });
});

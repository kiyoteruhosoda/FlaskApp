import { test, expect, Page, APIRequestContext } from '@playwright/test';

/**
 * 初期管理者フルスタック E2E。
 *
 * 実 FastAPI ＋ 実DB ＋ ビルド済み SPA に対し、admin@example.com / admin で
 * UI ログインし、App.tsx の全ルート（約30画面）を巡回する。
 *
 * 判定基準:
 *  - 各画面のルート要素（data-testid="*-page"）が表示されること
 *  - 画面遷移がログイン画面へ差し戻されない（＝認証・認可が有効）こと
 *  - API/Wiki API 応答に 5xx（サーバーエラー）・401/403（権限エラー）が無いこと
 *  - 未捕捉の JS 例外（pageerror）が無いこと
 *
 * パラメータ付きルートは事前に管理者トークンで最小フィクスチャ（アルバム／Wiki
 * ページ・カテゴリ）を API 経由で作成してから遷移する。セッション詳細・セレクション
 * エラー・スライドショーは実メディア／Picker 取り込みパイプラインを要するため、
 * 決定論的フィクスチャを用意できず本スイートの対象外とする。
 */

const ADMIN = { email: 'admin@example.com', password: 'admin' };

// ログイン後に到達可能な、パラメータを持たない静的ルート。
const STATIC_ROUTES: [path: string, testId: string][] = [
  ['/', 'home-page'],
  ['/dashboard', 'dashboard-page'],
  ['/profile', 'profile-page'],
  ['/media', 'media-page'],
  ['/media/duplicates', 'media-duplicates-page'],
  ['/albums', 'albums-page'],
  ['/tags', 'tags-page'],
  ['/jobs', 'jobs-page'],
  ['/sessions', 'sessions-page'],
  ['/photo-settings', 'photo-settings-page'],
  ['/photo-imports', 'photo-imports-page'],
  ['/admin/photo-exports', 'photo-exports-page'],
  ['/admin/users', 'users-page'],
  ['/admin/dashboard', 'admin-dashboard-page'],
  ['/admin/logs', 'system-logs-page'],
  ['/admin/roles', 'roles-page'],
  ['/admin/groups', 'groups-page'],
  ['/admin/permissions', 'permissions-page'],
  ['/admin/service-accounts', 'service-accounts-page'],
  ['/admin/config', 'config-page'],
  ['/admin/google-accounts', 'google-accounts-page'],
  ['/wiki', 'wiki-index-page'],
  ['/wiki/create', 'wiki-create-page'],
  ['/wiki/search', 'wiki-search-page'],
  ['/wiki/categories', 'wiki-categories-page'],
  ['/wiki/categories/create', 'wiki-create-category-page'],
  ['/wiki/admin', 'wiki-admin-page'],
];

/** 管理者トークンを取得する（SPA と同じく gui:view を要求して全保有権限を得る）。 */
async function loginApi(request: APIRequestContext): Promise<string> {
  const res = await request.post('/api/auth/login', {
    data: { email: ADMIN.email, password: ADMIN.password, scope: ['gui:view'] },
  });
  expect(res.ok(), `login failed: ${res.status()} ${await res.text()}`).toBeTruthy();
  return (await res.json()).access_token as string;
}

/** パラメータ付きルート用の最小フィクスチャを作成し、参照キーを返す。 */
async function createFixtures(
  request: APIRequestContext,
  token: string,
): Promise<{ albumId: number; pageSlug: string; categorySlug: string }> {
  const auth = { Authorization: `Bearer ${token}` };

  // アルバム（/albums/:id 用）
  const albumRes = await request.post('/api/albums', {
    headers: auth,
    data: { name: 'E2E Fullstack Album', description: 'fixture', visibility: 'private' },
  });
  expect(albumRes.ok(), `album create: ${albumRes.status()} ${await albumRes.text()}`).toBeTruthy();
  const albumId = (await albumRes.json()).album.id as number;

  // Wiki カテゴリ（/wiki/category/:slug 用）。既存なら 400 になり得るので許容する。
  const categorySlug = 'e2e-fullstack-cat';
  await request.post('/wiki/api/categories', {
    headers: auth,
    data: { name: 'E2E Fullstack Category', slug: categorySlug },
  });

  // Wiki ページ（/wiki/page|edit|history/:slug 用）。同上、既存なら許容する。
  const pageSlug = 'e2e-fullstack-page';
  await request.post('/wiki/api/pages', {
    headers: auth,
    data: { title: 'E2E Fullstack Page', slug: pageSlug, content: '# hello e2e' },
  });

  return { albumId, pageSlug, categorySlug };
}

/**
 * ページに API 応答・JS 例外の監視フックを取り付け、ルートごとにクリアして
 * 検査できるバッファを返す。
 */
function attachErrorProbes(page: Page) {
  const serverErrors: string[] = [];
  const authErrors: string[] = [];
  const jsErrors: string[] = [];

  page.on('response', (res) => {
    const url = res.url();
    if (!url.includes('/api/') && !url.includes('/wiki/api/')) return;
    const status = res.status();
    const path = new URL(url).pathname;
    if (status >= 500) serverErrors.push(`${status} ${path}`);
    else if (status === 401 || status === 403) authErrors.push(`${status} ${path}`);
  });
  page.on('pageerror', (err) => {
    jsErrors.push(err.message);
  });

  return {
    serverErrors,
    authErrors,
    jsErrors,
    reset() {
      serverErrors.length = 0;
      authErrors.length = 0;
      jsErrors.length = 0;
    },
  };
}

/** LoginPage から実際にログインし、/dashboard へ到達する。 */
async function uiLogin(page: Page): Promise<void> {
  await page.goto('/login');
  await page.fill('input[name="email"]', ADMIN.email);
  await page.fill('input[name="password"]', ADMIN.password);
  await page.getByTestId('login-submit').click();
  await page.waitForURL('**/dashboard', { timeout: 20_000 });
}

test('初期管理者で全画面を巡回してエラーが無いこと', async ({ page, request }) => {
  const token = await loginApi(request);
  const { albumId, pageSlug, categorySlug } = await createFixtures(request, token);

  const probes = attachErrorProbes(page);

  await uiLogin(page);

  const routes: [string, string][] = [
    ...STATIC_ROUTES,
    [`/albums/${albumId}`, 'album-detail-page'],
    [`/wiki/page/${pageSlug}`, 'wiki-page-detail-page'],
    [`/wiki/edit/${pageSlug}`, 'wiki-edit-page'],
    [`/wiki/history/${pageSlug}`, 'wiki-history-page'],
    [`/wiki/category/${categorySlug}`, 'wiki-category-page'],
  ];

  const problems: string[] = [];

  for (const [routePath, testId] of routes) {
    probes.reset();
    await page.goto(routePath);
    // XHR/描画が落ち着くのを待つ（一部画面はポーリングするため networkidle は使わない）
    await page.waitForTimeout(1500);

    const landed = new URL(page.url()).pathname;
    if (landed === '/login') {
      problems.push(`${routePath}: /login へ差し戻された（認証切れ/認可不足の疑い）`);
      continue;
    }

    const visible = await page
      .getByTestId(testId)
      .waitFor({ state: 'visible', timeout: 8000 })
      .then(() => true)
      .catch(() => false);
    if (!visible) {
      problems.push(`${routePath}: ルート要素 data-testid="${testId}" が表示されない`);
    }

    if (probes.serverErrors.length) {
      problems.push(`${routePath}: サーバーエラー応答 ${JSON.stringify(probes.serverErrors)}`);
    }
    if (probes.authErrors.length) {
      problems.push(`${routePath}: 権限エラー応答 ${JSON.stringify(probes.authErrors)}`);
    }
    if (probes.jsErrors.length) {
      problems.push(`${routePath}: JS 例外 ${JSON.stringify(probes.jsErrors)}`);
    }
  }

  expect(problems, `\n${problems.join('\n')}\n`).toEqual([]);
});

test('Profile のタイムゾーン設定が保存され現地時刻表示に反映される（T14）', async ({ page }) => {
  await uiLogin(page);

  await page.goto('/profile');
  await expect(page.getByTestId('timezone-settings')).toBeVisible();

  // 明示的に Asia/Tokyo を選択 → 保存されプレビューへ即時反映される。
  await page.getByTestId('timezone-select').selectOption('Asia/Tokyo');
  await expect(page.getByTestId('timezone-saved')).toBeVisible();
  await expect(page.getByTestId('timezone-preview')).toContainText('(Asia/Tokyo)');

  // リロード後も保存済みタイムゾーンが復元される（サーバー永続化＋起動時反映）。
  // select の値はサーバー設定の再取得（loadTimezone）で復元されるため、DB 永続化の検証になる。
  await page.reload();
  await expect(page.getByTestId('timezone-select')).toHaveValue('Asia/Tokyo');
  await expect(page.getByTestId('timezone-preview')).toContainText('(Asia/Tokyo)');

  // 後片付け: 自動（ブラウザ）へ戻して他テストへ影響を残さない。
  await page.getByTestId('timezone-select').selectOption('');
  await expect(page.getByTestId('timezone-saved')).toBeVisible();
});

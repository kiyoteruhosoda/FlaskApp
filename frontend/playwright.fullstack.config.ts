import { defineConfig, devices } from '@playwright/test';

/**
 * フルスタック E2E 設定。
 *
 * 既存の `playwright.config.ts`（API を全てモックする軽量スイート）とは別に、
 * 実 FastAPI サーバー ＋ 実DB（ファイルベース SQLite、マスタデータ投入済み）＋
 * ビルド済み SPA（FastAPI が `frontend/build` を配信）を起動し、初期管理者
 * （admin@example.com / admin）で実際にログインして全画面を巡回する。
 *
 * 重いテストのため既定スイートからは分離し、専用ジョブでの実行を想定する。
 *   npm run build   # 事前に SPA をビルド（webServer コマンドでも実行する）
 *   npx playwright test --config playwright.fullstack.config.ts
 *
 * Python 実行系は E2E_PYTHON 環境変数で差し替え可能（既定 `python`）。
 * ローカル検証例: E2E_PYTHON="uv run python" npx playwright test --config playwright.fullstack.config.ts
 */
const PORT = process.env.E2E_PORT || '8100';
const BASE = `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: './e2e-fullstack',
  timeout: 120_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: process.env.CI ? 'line' : [['list']],
  use: {
    baseURL: BASE,
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        // ブラウザが Playwright 既定パスに無い環境（プリインストール等）向けに、
        // PLAYWRIGHT_CHROMIUM_EXECUTABLE で実行ファイルを差し替えられるようにする。
        // 未設定なら Playwright 管理下のブラウザを使う（CI 既定）。
        ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE
          ? { launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE } }
          : {}),
      },
    },
  ],
  webServer: {
    // SPA を最新コードでビルドしてから実サーバーを起動する。
    command: 'npm run build && bash e2e-fullstack/run-server.sh',
    url: `${BASE}/api/version`,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
    env: {
      E2E_PORT: PORT,
      E2E_PYTHON: process.env.E2E_PYTHON || 'python',
    },
  },
});

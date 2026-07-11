import { test, expect } from '@playwright/test';

test.describe('Forgot Password', () => {
  test('shows forgot password form', async ({ page }) => {
    await page.goto('/forgot-password');
    await expect(page.getByTestId('forgot-password-page')).toBeVisible();
    await expect(page.getByTestId('forgot-password-submit')).toBeVisible();
  });

  test('shows success state after submission', async ({ page }) => {
    await page.route(
      (url) => url.pathname === '/api/auth/password/forgot',
      (route) => route.fulfill({ json: { sent: true } })
    );

    await page.goto('/forgot-password');
    await page.fill('input[name="email"]', 'test@example.com');
    await page.getByTestId('forgot-password-submit').click();

    await expect(page.getByTestId('forgot-password-success')).toBeVisible();
  });

  test('shows error on failure', async ({ page }) => {
    await page.route(
      (url) => url.pathname === '/api/auth/password/forgot',
      (route) => route.fulfill({ status: 500, json: { detail: { error: 'server_error' } } })
    );

    await page.goto('/forgot-password');
    await page.fill('input[name="email"]', 'test@example.com');
    await page.getByTestId('forgot-password-submit').click();

    await expect(page.getByTestId('forgot-password-error')).toBeVisible();
  });

  test('shows error when email service is not configured', async ({ page }) => {
    await page.route(
      (url) => url.pathname === '/api/auth/password/forgot',
      (route) => route.fulfill({ status: 503, json: { detail: { error: 'mail_disabled' } } })
    );

    await page.goto('/forgot-password');
    await page.fill('input[name="email"]', 'test@example.com');
    await page.getByTestId('forgot-password-submit').click();

    await expect(page.getByTestId('forgot-password-error')).toBeVisible();
    await expect(page.getByText('Mail service not configured')).toBeVisible();
  });
});

test.describe('Reset Password', () => {
  test('shows error when no token in URL', async ({ page }) => {
    await page.goto('/reset-password');
    await expect(page.getByTestId('reset-password-page')).toBeVisible();
    await expect(page.getByText('無効または期限切れのリセットトークンです')).toBeVisible();
    await expect(page.getByTestId('reset-password-submit')).not.toBeVisible();
  });

  test('shows form when token is present', async ({ page }) => {
    await page.goto('/reset-password?token=valid-token-123');
    await expect(page.getByTestId('reset-password-page')).toBeVisible();
    await expect(page.getByTestId('reset-password-submit')).toBeVisible();
  });

  test('validates passwords match', async ({ page }) => {
    await page.goto('/reset-password?token=valid-token-123');
    await page.fill('input[name="new_password"]', 'password123');
    await page.fill('input[name="confirm_password"]', 'different456');
    await page.getByTestId('reset-password-submit').click();

    await expect(page.getByTestId('reset-password-error')).toBeVisible();
    await expect(page.getByText('パスワードが一致しません')).toBeVisible();
  });

  test('validates minimum password length', async ({ page }) => {
    await page.goto('/reset-password?token=valid-token-123');
    await page.fill('input[name="new_password"]', 'short');
    await page.fill('input[name="confirm_password"]', 'short');
    await page.getByTestId('reset-password-submit').click();

    await expect(page.getByTestId('reset-password-error')).toBeVisible();
    await expect(page.getByText('パスワードは8文字以上で入力してください')).toBeVisible();
  });

  test('resets password successfully and redirects to login', async ({ page }) => {
    await page.route(
      (url) => url.pathname === '/api/auth/password/reset',
      (route) => route.fulfill({ json: { reset: true } })
    );

    await page.goto('/reset-password?token=valid-token-123');
    await page.fill('input[name="new_password"]', 'newpassword123');
    await page.fill('input[name="confirm_password"]', 'newpassword123');
    await page.getByTestId('reset-password-submit').click();

    await page.waitForURL('/login');
  });

  test('shows error for invalid token from API', async ({ page }) => {
    await page.route(
      (url) => url.pathname === '/api/auth/password/reset',
      (route) => route.fulfill({ status: 400, json: { detail: { error: 'invalid_token' } } })
    );

    await page.goto('/reset-password?token=bad-token');
    await page.fill('input[name="new_password"]', 'newpassword123');
    await page.fill('input[name="confirm_password"]', 'newpassword123');
    await page.getByTestId('reset-password-submit').click();

    await expect(page.getByTestId('reset-password-error')).toBeVisible();
    await expect(page.getByText('無効または期限切れのリセットトークンです')).toBeVisible();
  });
});

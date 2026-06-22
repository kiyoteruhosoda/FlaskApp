import { test, expect } from '@playwright/test';
import { setupAuth, TEST_USER } from './helpers';

const TOKENS = { access_token: 'acc', refresh_token: 'ref' };

test.describe('Register', () => {
  test('redirects to / when already authenticated', async ({ page }) => {
    await setupAuth(page);
    await page.goto('/register');
    await expect(page).toHaveURL('/');
  });

  test('shows registration form', async ({ page }) => {
    await page.goto('/register');
    await expect(page.getByTestId('register-page')).toBeVisible();
    await expect(page.locator('input[name="email"]')).toBeVisible();
    await expect(page.locator('input[name="password"]')).toBeVisible();
    await expect(page.locator('input[name="confirm_password"]')).toBeVisible();
    await expect(page.getByTestId('register-submit')).toBeVisible();
  });

  test('shows error when passwords do not match', async ({ page }) => {
    await page.goto('/register');
    await page.fill('input[name="email"]', 'new@example.com');
    await page.fill('input[name="password"]', 'password1');
    await page.fill('input[name="confirm_password"]', 'password2');
    await page.getByTestId('register-submit').click();
    await expect(page.getByTestId('register-error')).toContainText('パスワードが一致しません');
  });

  test('shows error when password is too short', async ({ page }) => {
    await page.goto('/register');
    await page.fill('input[name="email"]', 'new@example.com');
    await page.fill('input[name="password"]', 'short');
    await page.fill('input[name="confirm_password"]', 'short');
    await page.getByTestId('register-submit').click();
    await expect(page.getByTestId('register-error')).toContainText('8');
  });

  test('successful registration navigates to /', async ({ page }) => {
    await page.route(
      (url) => url.pathname === '/api/auth/register',
      (route) => route.fulfill({ status: 201, json: { ...TOKENS, user: { id: 2, email: 'new@example.com', username: null } } })
    );
    await page.route(
      (url) => url.pathname === '/api/auth/me',
      (route) => route.fulfill({ json: { ...TEST_USER, email: 'new@example.com' } })
    );
    await page.route(
      (url) => url.pathname === '/api/auth/roles',
      (route) => route.fulfill({ json: { roles: TEST_USER.roles } })
    );

    await page.goto('/register');
    await page.fill('input[name="email"]', 'new@example.com');
    await page.fill('input[name="password"]', 'password123');
    await page.fill('input[name="confirm_password"]', 'password123');
    await page.getByTestId('register-submit').click();

    await expect(page).toHaveURL('/');
  });

  test('shows error when email already in use', async ({ page }) => {
    await page.route(
      (url) => url.pathname === '/api/auth/register',
      (route) => route.fulfill({ status: 409, json: { error: 'email_exists' } })
    );

    await page.goto('/register');
    await page.fill('input[name="email"]', 'admin@example.com');
    await page.fill('input[name="password"]', 'password123');
    await page.fill('input[name="confirm_password"]', 'password123');
    await page.getByTestId('register-submit').click();

    await expect(page.getByTestId('register-error')).toContainText('すでに使用されています');
    await expect(page).toHaveURL('/register');
  });
});

import { test, expect } from '@playwright/test';
import { setupAuth } from './helpers';

const MOCK_STATS = {
  users: { total: 42, active: 38 },
  roles: 5,
  groups: 3,
  serviceAccounts: 2,
  recentJobs: [
    { id: 1, target: 'google_photos', status: 'success', startedAt: '2024-06-01T10:00:00Z' },
    { id: 2, target: 'local_import', status: 'failed', startedAt: '2024-06-02T11:00:00Z' },
  ],
};

const MOCK_ROLES = [
  { id: 1, name: 'admin', permissions: ['admin:system-settings', 'user:manage'] },
  { id: 2, name: 'viewer', permissions: ['media:view'] },
];

const MOCK_PERMISSIONS = [
  { id: 1, code: 'media:view', detail: 'View media files', roleCount: 3 },
  { id: 2, code: 'admin:system-settings', detail: 'Manage system settings', roleCount: 1 },
];

const MOCK_GROUPS = [
  { id: 1, name: 'Family', description: 'Family members', parentId: null, parentName: null, memberCount: 5, childCount: 1 },
  { id: 2, name: 'Kids', description: '', parentId: 1, parentName: 'Family', memberCount: 2, childCount: 0 },
];

const MOCK_SERVICE_ACCOUNTS = [
  { id: 1, name: 'backup-bot', description: 'Backup service', scopes: ['media:view'], isActive: true, createdAt: '2024-01-01T00:00:00Z', updatedAt: '2024-01-01T00:00:00Z' },
];

// ===== Admin Dashboard =====

test.describe('Admin Dashboard', () => {
  test('shows statistics', async ({ page }) => {
    await setupAuth(page);
    await page.route(
      (url) => url.pathname === '/api/admin/dashboard',
      (route) => route.fulfill({ json: { stats: MOCK_STATS } })
    );

    await page.goto('/admin/dashboard');
    await expect(page.getByTestId('admin-dashboard-page')).toBeVisible();
    await expect(page.getByText('42')).toBeVisible();
    await expect(page.getByText('38')).toBeVisible();
  });

  test('shows recent jobs table', async ({ page }) => {
    await setupAuth(page);
    await page.route(
      (url) => url.pathname === '/api/admin/dashboard',
      (route) => route.fulfill({ json: { stats: MOCK_STATS } })
    );

    await page.goto('/admin/dashboard');
    await expect(page.getByText('google_photos')).toBeVisible();
    await expect(page.getByText('success')).toBeVisible();
    await expect(page.getByText('failed')).toBeVisible();
  });

  test('shows error on 403', async ({ page }) => {
    await setupAuth(page);
    await page.route(
      (url) => url.pathname === '/api/admin/dashboard',
      (route) => route.fulfill({ status: 403, json: {} })
    );

    await page.goto('/admin/dashboard');
    await expect(page.getByText('You do not have permission to view this page')).toBeVisible();
  });
});

// ===== Roles =====

test.describe('Roles Page', () => {
  test('shows roles table', async ({ page }) => {
    await setupAuth(page);
    await page.route(
      (url) => url.pathname === '/api/admin/roles',
      (route) => route.fulfill({ json: { roles: MOCK_ROLES } })
    );
    await page.route(
      (url) => url.pathname === '/api/admin/permissions',
      (route) => route.fulfill({ json: { permissions: MOCK_PERMISSIONS } })
    );

    await page.goto('/admin/roles');
    await expect(page.getByTestId('roles-page')).toBeVisible();
    await expect(page.getByTestId('roles-table')).toBeVisible();
    await expect(page.getByText('admin')).toBeVisible();
    await expect(page.getByText('viewer')).toBeVisible();
  });

  test('shows empty state', async ({ page }) => {
    await setupAuth(page);
    await page.route((url) => url.pathname === '/api/admin/roles', (route) => route.fulfill({ json: { roles: [] } }));
    await page.route((url) => url.pathname === '/api/admin/permissions', (route) => route.fulfill({ json: { permissions: [] } }));

    await page.goto('/admin/roles');
    await expect(page.getByTestId('roles-empty')).toBeVisible();
  });

  test('creates a new role', async ({ page }) => {
    await setupAuth(page);
    await page.route((url) => url.pathname === '/api/admin/roles', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({ json: { roles: MOCK_ROLES } });
      } else {
        await route.fulfill({ json: { role: { id: 3, name: 'editor', permissions: [] }, created: true } });
      }
    });
    await page.route((url) => url.pathname === '/api/admin/permissions', (route) => route.fulfill({ json: { permissions: MOCK_PERMISSIONS } }));

    await page.goto('/admin/roles');
    await page.getByTestId('roles-create').click();
    await page.fill('[data-testid="role-form-name"]', 'editor');
    await page.getByTestId('role-form-submit').click();

    await expect(page.getByTestId('roles-table')).toBeVisible();
  });

  test('opens delete confirm dialog', async ({ page }) => {
    await setupAuth(page);
    await page.route((url) => url.pathname === '/api/admin/roles', (route) => route.fulfill({ json: { roles: MOCK_ROLES } }));
    await page.route((url) => url.pathname === '/api/admin/permissions', (route) => route.fulfill({ json: { permissions: [] } }));

    await page.goto('/admin/roles');
    await page.getByTestId('role-delete').first().click();
    await expect(page.getByTestId('role-delete-confirm')).toBeVisible();
  });
});

// ===== Groups =====

test.describe('Groups Page', () => {
  test('shows groups table', async ({ page }) => {
    await setupAuth(page);
    await page.route(
      (url) => url.pathname === '/api/admin/groups',
      (route) => route.fulfill({ json: { groups: MOCK_GROUPS } })
    );

    await page.goto('/admin/groups');
    await expect(page.getByTestId('groups-page')).toBeVisible();
    await expect(page.getByTestId('groups-table')).toBeVisible();
    await expect(page.getByText('Family')).toBeVisible();
    await expect(page.getByText('Kids')).toBeVisible();
  });

  test('shows empty state', async ({ page }) => {
    await setupAuth(page);
    await page.route((url) => url.pathname === '/api/admin/groups', (route) => route.fulfill({ json: { groups: [] } }));

    await page.goto('/admin/groups');
    await expect(page.getByTestId('groups-empty')).toBeVisible();
  });

  test('creates a new group', async ({ page }) => {
    await setupAuth(page);
    await page.route((url) => url.pathname === '/api/admin/groups', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({ json: { groups: MOCK_GROUPS } });
      } else {
        await route.fulfill({ json: { group: { id: 3, name: 'Friends', description: '', parentId: null, parentName: null, memberCount: 0, childCount: 0 }, created: true } });
      }
    });

    await page.goto('/admin/groups');
    await page.getByTestId('groups-create').click();
    await page.fill('[data-testid="group-form-name"]', 'Friends');
    await page.getByTestId('group-form-submit').click();

    await expect(page.getByTestId('groups-table')).toBeVisible();
  });

  test('opens delete confirm dialog', async ({ page }) => {
    await setupAuth(page);
    await page.route((url) => url.pathname === '/api/admin/groups', (route) => route.fulfill({ json: { groups: MOCK_GROUPS } }));

    await page.goto('/admin/groups');
    await page.getByTestId('group-delete').first().click();
    await expect(page.getByTestId('group-delete-confirm')).toBeVisible();
  });
});

// ===== Permissions =====

test.describe('Permissions Page', () => {
  test('shows permissions table', async ({ page }) => {
    await setupAuth(page);
    await page.route(
      (url) => url.pathname === '/api/admin/permissions',
      (route) => route.fulfill({ json: { permissions: MOCK_PERMISSIONS } })
    );

    await page.goto('/admin/permissions');
    await expect(page.getByTestId('permissions-page')).toBeVisible();
    await expect(page.getByTestId('permissions-table')).toBeVisible();
    await expect(page.getByText('media:view')).toBeVisible();
  });

  test('shows empty state', async ({ page }) => {
    await setupAuth(page);
    await page.route((url) => url.pathname === '/api/admin/permissions', (route) => route.fulfill({ json: { permissions: [] } }));

    await page.goto('/admin/permissions');
    await expect(page.getByTestId('permissions-empty')).toBeVisible();
  });

  test('creates a new permission', async ({ page }) => {
    await setupAuth(page);
    await page.route((url) => url.pathname === '/api/admin/permissions', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({ json: { permissions: MOCK_PERMISSIONS } });
      } else {
        await route.fulfill({ json: { permission: { id: 3, code: 'album:write', detail: '', roleCount: 0 }, created: true } });
      }
    });

    await page.goto('/admin/permissions');
    await page.getByTestId('permissions-create').click();
    await page.fill('[data-testid="permission-form-code"]', 'album:write');
    await page.getByTestId('permission-form-submit').click();

    await expect(page.getByTestId('permissions-table')).toBeVisible();
  });

  test('searches permissions', async ({ page }) => {
    await setupAuth(page);
    let callCount = 0;
    await page.route((url) => url.pathname === '/api/admin/permissions', (route) => {
      callCount += 1;
      route.fulfill({ json: { permissions: callCount === 1 ? MOCK_PERMISSIONS : [MOCK_PERMISSIONS[0]] } });
    });

    await page.goto('/admin/permissions');
    await page.fill('[data-testid="permissions-search"]', 'media');
    await page.getByRole('button', { name: 'Search' }).click();

    await expect(page.getByTestId('permissions-table')).toBeVisible();
  });

  test('opens delete confirm dialog', async ({ page }) => {
    await setupAuth(page);
    await page.route((url) => url.pathname === '/api/admin/permissions', (route) => route.fulfill({ json: { permissions: MOCK_PERMISSIONS } }));

    await page.goto('/admin/permissions');
    await page.getByTestId('permission-delete').first().click();
    await expect(page.getByTestId('permission-delete-confirm')).toBeVisible();
  });
});

// ===== Service Accounts =====

test.describe('Service Accounts Page', () => {
  test('shows service accounts table', async ({ page }) => {
    await setupAuth(page);
    await page.route(
      (url) => url.pathname === '/api/admin/service-accounts',
      (route) => route.fulfill({ json: { serviceAccounts: MOCK_SERVICE_ACCOUNTS } })
    );

    await page.goto('/admin/service-accounts');
    await expect(page.getByTestId('service-accounts-page')).toBeVisible();
    await expect(page.getByTestId('sa-table')).toBeVisible();
    await expect(page.getByText('backup-bot')).toBeVisible();
  });

  test('shows empty state', async ({ page }) => {
    await setupAuth(page);
    await page.route((url) => url.pathname === '/api/admin/service-accounts', (route) => route.fulfill({ json: { serviceAccounts: [] } }));

    await page.goto('/admin/service-accounts');
    await expect(page.getByTestId('sa-empty')).toBeVisible();
  });

  test('creates a new service account', async ({ page }) => {
    await setupAuth(page);
    await page.route((url) => url.pathname === '/api/admin/service-accounts', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({ json: { serviceAccounts: MOCK_SERVICE_ACCOUNTS } });
      } else {
        await route.fulfill({ json: { serviceAccount: { id: 2, name: 'new-bot', description: '', scopes: [], isActive: true, createdAt: '2024-01-01T00:00:00Z', updatedAt: '2024-01-01T00:00:00Z' }, created: true } });
      }
    });

    await page.goto('/admin/service-accounts');
    await page.getByTestId('sa-create').click();
    await page.fill('[data-testid="sa-form-name"]', 'new-bot');
    await page.getByTestId('sa-form-submit').click();

    await expect(page.getByTestId('sa-table')).toBeVisible();
  });

  test('opens delete confirm dialog', async ({ page }) => {
    await setupAuth(page);
    await page.route((url) => url.pathname === '/api/admin/service-accounts', (route) => route.fulfill({ json: { serviceAccounts: MOCK_SERVICE_ACCOUNTS } }));

    await page.goto('/admin/service-accounts');
    await page.getByTestId('sa-delete').first().click();
    await expect(page.getByTestId('sa-delete-confirm')).toBeVisible();
  });
});

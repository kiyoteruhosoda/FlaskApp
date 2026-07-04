import React from 'react';
import { Nav } from 'react-bootstrap';
import { useSelector } from 'react-redux';
import { RootState } from '../store';
import { useTranslation } from 'react-i18next';
import { Link, useLocation } from 'react-router-dom';

const Sidebar: React.FC = () => {
  const { t } = useTranslation();
  const location = useLocation();
  const { user } = useSelector((state: RootState) => state.auth);
  const { sidebarCollapsed } = useSelector((state: RootState) => state.ui);

  const hasPermission = (permission: string): boolean => {
    return user?.permissions?.includes(permission) || false;
  };

  const isActive = (path: string): boolean => {
    return location.pathname === path;
  };

  if (!user) return null;

  return (
    <div
      className={`bg-light border-end vh-100 position-sticky top-0 ${
        sidebarCollapsed ? 'd-none d-md-block' : ''
      }`}
      style={{
        width: sidebarCollapsed ? '60px' : '250px',
        transition: 'width 0.3s ease',
        minHeight: '100vh'
      }}
    >
      <div className="p-3">
        <Nav className="flex-column">
          <Nav.Link
            as={Link}
            to="/"
            className={`d-flex align-items-center py-2 ${isActive('/') ? 'active' : ''}`}
          >
            <i className="fa-solid fa-house me-2"></i>
            {!sidebarCollapsed && <span>{t('Home')}</span>}
          </Nav.Link>

          {hasPermission('dashboard:view') && (
            <Nav.Link
              as={Link}
              to="/dashboard"
              className={`d-flex align-items-center py-2 ${isActive('/dashboard') ? 'active' : ''}`}
            >
              <i className="fa-solid fa-bars-progress me-2"></i>
              {!sidebarCollapsed && <span>{t('Dashboard')}</span>}
            </Nav.Link>
          )}

          {hasPermission('media:view') && (
            <>
              <div className="mt-3 mb-2">
                {!sidebarCollapsed && (
                  <small className="text-muted text-uppercase fw-bold px-2">
                    {t('Media')}
                  </small>
                )}
              </div>

              {/* 表示系: 閲覧用のページ */}
              <Nav.Link
                as={Link}
                to="/media"
                className={`d-flex align-items-center py-2 ${isActive('/media') ? 'active' : ''}`}
              >
                <i className="fa-solid fa-images me-2"></i>
                {!sidebarCollapsed && <span>{t('Media Gallery')}</span>}
              </Nav.Link>

              {hasPermission('album:view') && (
                <Nav.Link
                  as={Link}
                  to="/albums"
                  className={`d-flex align-items-center py-2 ${isActive('/albums') ? 'active' : ''}`}
                >
                  <i className="fa-solid fa-book me-2"></i>
                  {!sidebarCollapsed && <span>{t('Albums')}</span>}
                </Nav.Link>
              )}

              <Nav.Link
                as={Link}
                to="/tags"
                className={`d-flex align-items-center py-2 ${isActive('/tags') ? 'active' : ''}`}
              >
                <i className="fa-solid fa-tags me-2"></i>
                {!sidebarCollapsed && <span>{t('Tags')}</span>}
              </Nav.Link>

              {hasPermission('media:delete') && (
                <Nav.Link
                  as={Link}
                  to="/media/duplicates"
                  className={`d-flex align-items-center py-2 ${isActive('/media/duplicates') ? 'active' : ''}`}
                >
                  <i className="fa-solid fa-layer-group me-2"></i>
                  {!sidebarCollapsed && <span>{t('Duplicates')}</span>}
                </Nav.Link>
              )}

              {/* 管理系: 同期・設定用のページ */}
              {hasPermission('media:session') && (
                <Nav.Link
                  as={Link}
                  to="/sessions"
                  className={`d-flex align-items-center py-2 ${isActive('/sessions') ? 'active' : ''}`}
                >
                  <i className="fa-solid fa-layer-group me-2"></i>
                  {!sidebarCollapsed && <span>{t('Sessions')}</span>}
                </Nav.Link>
              )}

              {hasPermission('media:session') && (
                <Nav.Link
                  as={Link}
                  to="/jobs"
                  className={`d-flex align-items-center py-2 ${isActive('/jobs') ? 'active' : ''}`}
                >
                  <i className="fa-solid fa-list-check me-2"></i>
                  {!sidebarCollapsed && <span>{t('Sync Jobs')}</span>}
                </Nav.Link>
              )}

              {hasPermission('admin:photo-settings') && (
                <Nav.Link
                  as={Link}
                  to="/photo-imports"
                  className={`d-flex align-items-center py-2 ${isActive('/photo-imports') ? 'active' : ''}`}
                >
                  <i className="fa-solid fa-file-import me-2"></i>
                  {!sidebarCollapsed && <span>{t('Photo Imports')}</span>}
                </Nav.Link>
              )}

              {hasPermission('admin:photo-settings') && (
                <Nav.Link
                  as={Link}
                  to="/photo-settings"
                  className={`d-flex align-items-center py-2 ${isActive('/photo-settings') ? 'active' : ''}`}
                >
                  <i className="fa-solid fa-sliders me-2"></i>
                  {!sidebarCollapsed && <span>{t('Photo Settings')}</span>}
                </Nav.Link>
              )}
            </>
          )}

          {(hasPermission('admin:system-settings') || hasPermission('user:manage')) && (
            <>
              <div className="mt-3 mb-2">
                {!sidebarCollapsed && (
                  <small className="text-muted text-uppercase fw-bold px-2">
                    {t('Administration')}
                  </small>
                )}
              </div>

              {hasPermission('admin:system-settings') && (
                <Nav.Link
                  as={Link}
                  to="/admin/dashboard"
                  className={`d-flex align-items-center py-2 ${isActive('/admin/dashboard') ? 'active' : ''}`}
                >
                  <i className="fa-solid fa-server me-2"></i>
                  {!sidebarCollapsed && <span>{t('System Overview')}</span>}
                </Nav.Link>
              )}

              {hasPermission('user:manage') && (
                <Nav.Link
                  as={Link}
                  to="/admin/users"
                  className={`d-flex align-items-center py-2 ${isActive('/admin/users') ? 'active' : ''}`}
                >
                  <i className="fa-solid fa-users me-2"></i>
                  {!sidebarCollapsed && <span>{t('Users')}</span>}
                </Nav.Link>
              )}

              {hasPermission('user:manage') && (
                <Nav.Link
                  as={Link}
                  to="/admin/roles"
                  className={`d-flex align-items-center py-2 ${isActive('/admin/roles') ? 'active' : ''}`}
                >
                  <i className="fa-solid fa-shield-halved me-2"></i>
                  {!sidebarCollapsed && <span>{t('Roles')}</span>}
                </Nav.Link>
              )}

              {hasPermission('user:manage') && (
                <Nav.Link
                  as={Link}
                  to="/admin/groups"
                  className={`d-flex align-items-center py-2 ${isActive('/admin/groups') ? 'active' : ''}`}
                >
                  <i className="fa-solid fa-sitemap me-2"></i>
                  {!sidebarCollapsed && <span>{t('Groups')}</span>}
                </Nav.Link>
              )}

              {hasPermission('admin:system-settings') && (
                <Nav.Link
                  as={Link}
                  to="/admin/permissions"
                  className={`d-flex align-items-center py-2 ${isActive('/admin/permissions') ? 'active' : ''}`}
                >
                  <i className="fa-solid fa-key me-2"></i>
                  {!sidebarCollapsed && <span>{t('Permissions')}</span>}
                </Nav.Link>
              )}

              {hasPermission('admin:system-settings') && (
                <Nav.Link
                  as={Link}
                  to="/admin/service-accounts"
                  className={`d-flex align-items-center py-2 ${isActive('/admin/service-accounts') ? 'active' : ''}`}
                >
                  <i className="fa-solid fa-robot me-2"></i>
                  {!sidebarCollapsed && <span>{t('Service Accounts')}</span>}
                </Nav.Link>
              )}

              {hasPermission('system:manage') && (
                <Nav.Link
                  as={Link}
                  to="/admin/config"
                  className={`d-flex align-items-center py-2 ${isActive('/admin/config') ? 'active' : ''}`}
                >
                  <i className="fa-solid fa-gear me-2"></i>
                  {!sidebarCollapsed && <span>{t('System Settings')}</span>}
                </Nav.Link>
              )}

              {hasPermission('admin:system-settings') && (
                <Nav.Link
                  as={Link}
                  to="/admin/google-accounts"
                  className={`d-flex align-items-center py-2 ${isActive('/admin/google-accounts') ? 'active' : ''}`}
                >
                  <i className="fa-brands fa-google me-2"></i>
                  {!sidebarCollapsed && <span>{t('Google Accounts')}</span>}
                </Nav.Link>
              )}

              {hasPermission('system:manage') && (
                <Nav.Link
                  as={Link}
                  to="/admin/photo-exports"
                  className={`d-flex align-items-center py-2 ${isActive('/admin/photo-exports') ? 'active' : ''}`}
                >
                  <i className="fa-solid fa-file-export me-2"></i>
                  {!sidebarCollapsed && <span>{t('Photo Exports')}</span>}
                </Nav.Link>
              )}
            </>
          )}
        </Nav>
      </div>
    </div>
  );
};

export default Sidebar;

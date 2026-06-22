import React from 'react';
import { Nav } from 'react-bootstrap';
import { useSelector } from 'react-redux';
import { RootState } from '../store';
import { useTranslation } from 'react-i18next';
import { useLocation } from 'react-router-dom';

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
            href="/" 
            className={`d-flex align-items-center py-2 ${isActive('/') ? 'active' : ''}`}
          >
            <i className="bi bi-house-door me-2"></i>
            {!sidebarCollapsed && <span>{t('Home')}</span>}
          </Nav.Link>

          {hasPermission('dashboard:view') && (
            <Nav.Link 
              href="/dashboard" 
              className={`d-flex align-items-center py-2 ${isActive('/dashboard') ? 'active' : ''}`}
            >
              <i className="bi bi-speedometer2 me-2"></i>
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

              {hasPermission('media:session') && (
                <Nav.Link
                  href="/sessions"
                  className={`d-flex align-items-center py-2 ${isActive('/sessions') ? 'active' : ''}`}
                >
                  <i className="bi bi-collection me-2"></i>
                  {!sidebarCollapsed && <span>{t('Sessions')}</span>}
                </Nav.Link>
              )}

              {hasPermission('media:session') && (
                <Nav.Link
                  href="/jobs"
                  className={`d-flex align-items-center py-2 ${isActive('/jobs') ? 'active' : ''}`}
                >
                  <i className="bi bi-list-task me-2"></i>
                  {!sidebarCollapsed && <span>{t('Sync Jobs')}</span>}
                </Nav.Link>
              )}

              <Nav.Link 
                href="/media" 
                className={`d-flex align-items-center py-2 ${isActive('/media') ? 'active' : ''}`}
              >
                <i className="bi bi-images me-2"></i>
                {!sidebarCollapsed && <span>{t('Media Gallery')}</span>}
              </Nav.Link>

              {hasPermission('album:view') && (
                <Nav.Link 
                  href="/albums" 
                  className={`d-flex align-items-center py-2 ${isActive('/albums') ? 'active' : ''}`}
                >
                  <i className="bi bi-book me-2"></i>
                  {!sidebarCollapsed && <span>{t('Albums')}</span>}
                </Nav.Link>
              )}

              <Nav.Link
                href="/tags"
                className={`d-flex align-items-center py-2 ${isActive('/tags') ? 'active' : ''}`}
              >
                <i className="bi bi-tags me-2"></i>
                {!sidebarCollapsed && <span>{t('Tags')}</span>}
              </Nav.Link>

              {hasPermission('admin:photo-settings') && (
                <Nav.Link
                  href="/photo-settings"
                  className={`d-flex align-items-center py-2 ${isActive('/photo-settings') ? 'active' : ''}`}
                >
                  <i className="bi bi-sliders me-2"></i>
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
                  href="/admin/dashboard"
                  className={`d-flex align-items-center py-2 ${isActive('/admin/dashboard') ? 'active' : ''}`}
                >
                  <i className="bi bi-speedometer2 me-2"></i>
                  {!sidebarCollapsed && <span>{t('System Overview')}</span>}
                </Nav.Link>
              )}

              {hasPermission('user:manage') && (
                <Nav.Link
                  href="/admin/users"
                  className={`d-flex align-items-center py-2 ${isActive('/admin/users') ? 'active' : ''}`}
                >
                  <i className="bi bi-people me-2"></i>
                  {!sidebarCollapsed && <span>{t('Users')}</span>}
                </Nav.Link>
              )}

              {hasPermission('user:manage') && (
                <Nav.Link
                  href="/admin/roles"
                  className={`d-flex align-items-center py-2 ${isActive('/admin/roles') ? 'active' : ''}`}
                >
                  <i className="bi bi-shield me-2"></i>
                  {!sidebarCollapsed && <span>{t('Roles')}</span>}
                </Nav.Link>
              )}

              {hasPermission('user:manage') && (
                <Nav.Link
                  href="/admin/groups"
                  className={`d-flex align-items-center py-2 ${isActive('/admin/groups') ? 'active' : ''}`}
                >
                  <i className="bi bi-diagram-3 me-2"></i>
                  {!sidebarCollapsed && <span>{t('Groups')}</span>}
                </Nav.Link>
              )}

              {hasPermission('admin:system-settings') && (
                <Nav.Link
                  href="/admin/permissions"
                  className={`d-flex align-items-center py-2 ${isActive('/admin/permissions') ? 'active' : ''}`}
                >
                  <i className="bi bi-key me-2"></i>
                  {!sidebarCollapsed && <span>{t('Permissions')}</span>}
                </Nav.Link>
              )}

              {hasPermission('admin:system-settings') && (
                <Nav.Link
                  href="/admin/service-accounts"
                  className={`d-flex align-items-center py-2 ${isActive('/admin/service-accounts') ? 'active' : ''}`}
                >
                  <i className="bi bi-robot me-2"></i>
                  {!sidebarCollapsed && <span>{t('Service Accounts')}</span>}
                </Nav.Link>
              )}

              {hasPermission('system:manage') && (
                <Nav.Link
                  href="/admin/config"
                  className={`d-flex align-items-center py-2 ${isActive('/admin/config') ? 'active' : ''}`}
                >
                  <i className="bi bi-gear me-2"></i>
                  {!sidebarCollapsed && <span>{t('System Settings')}</span>}
                </Nav.Link>
              )}

              {hasPermission('admin:system-settings') && (
                <Nav.Link
                  href="/admin/google-accounts"
                  className={`d-flex align-items-center py-2 ${isActive('/admin/google-accounts') ? 'active' : ''}`}
                >
                  <i className="bi bi-google me-2"></i>
                  {!sidebarCollapsed && <span>{t('Google Accounts')}</span>}
                </Nav.Link>
              )}

              {hasPermission('system:manage') && (
                <Nav.Link
                  href="/admin/photo-exports"
                  className={`d-flex align-items-center py-2 ${isActive('/admin/photo-exports') ? 'active' : ''}`}
                >
                  <i className="bi bi-box-arrow-up me-2"></i>
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
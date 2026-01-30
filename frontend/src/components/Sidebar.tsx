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
            </>
          )}

          {hasPermission('admin:system-settings') && (
            <>
              <div className="mt-3 mb-2">
                {!sidebarCollapsed && (
                  <small className="text-muted text-uppercase fw-bold px-2">
                    {t('Administration')}
                  </small>
                )}
              </div>

              <Nav.Link 
                href="/admin/users" 
                className={`d-flex align-items-center py-2 ${isActive('/admin/users') ? 'active' : ''}`}
              >
                <i className="bi bi-people me-2"></i>
                {!sidebarCollapsed && <span>{t('Users')}</span>}
              </Nav.Link>

              <Nav.Link 
                href="/admin/system-settings" 
                className={`d-flex align-items-center py-2 ${isActive('/admin/system-settings') ? 'active' : ''}`}
              >
                <i className="bi bi-gear me-2"></i>
                {!sidebarCollapsed && <span>{t('System Settings')}</span>}
              </Nav.Link>

              <Nav.Link 
                href="/admin/google-accounts" 
                className={`d-flex align-items-center py-2 ${isActive('/admin/google-accounts') ? 'active' : ''}`}
              >
                <i className="bi bi-google me-2"></i>
                {!sidebarCollapsed && <span>{t('Google Accounts')}</span>}
              </Nav.Link>
            </>
          )}
        </Nav>
      </div>
    </div>
  );
};

export default Sidebar;
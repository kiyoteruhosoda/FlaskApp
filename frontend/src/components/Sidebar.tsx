import React, { useState } from 'react';
import { Nav, Offcanvas } from 'react-bootstrap';
import { useDispatch, useSelector } from 'react-redux';
import { RootState } from '../store';
import { useTranslation } from 'react-i18next';
import { Link, useLocation } from 'react-router-dom';
import { setMobileSidebarOpen } from '../store/uiSlice';

interface NavItem {
  to: string;
  icon: string;
  label: string;
  permission?: string;
}

// カテゴリ開閉状態を localStorage に永続化するキー
const categoryStorageKey = (id: string) => `sidebar.category.${id}`;

const Sidebar: React.FC = () => {
  const { t } = useTranslation();
  const dispatch = useDispatch();
  const location = useLocation();
  const { user } = useSelector((state: RootState) => state.auth);
  const { sidebarCollapsed, mobileSidebarOpen } = useSelector((state: RootState) => state.ui);

  const [openCategories, setOpenCategories] = useState<Record<string, boolean>>(() => {
    const initial: Record<string, boolean> = {};
    for (const id of ['media', 'import', 'admin']) {
      initial[id] = localStorage.getItem(categoryStorageKey(id)) !== 'closed';
    }
    return initial;
  });

  const hasPermission = (permission: string): boolean => {
    return user?.permissions?.includes(permission) || false;
  };

  const isActive = (path: string): boolean => {
    return location.pathname === path;
  };

  // モバイルではリンクをタップしたらオフキャンバスを閉じる
  const closeMobileSidebar = () => dispatch(setMobileSidebarOpen(false));

  const toggleCategory = (id: string) => {
    setOpenCategories((prev) => {
      const next = { ...prev, [id]: !prev[id] };
      localStorage.setItem(categoryStorageKey(id), next[id] ? 'open' : 'closed');
      return next;
    });
  };

  if (!user) return null;

  const renderItem = (item: NavItem) => (
    <Nav.Link
      key={item.to}
      as={Link}
      to={item.to}
      onClick={closeMobileSidebar}
      className={`d-flex align-items-center py-2 ${isActive(item.to) ? 'active' : ''}`}
    >
      {/* fa-brands 指定（Google 等）はそのまま使い、それ以外は fa-solid を補う */}
      <i className={`${item.icon.startsWith('fa-brands') ? item.icon : `fa-solid ${item.icon}`} me-2`}></i>
      <span className="sidebar-label">{t(item.label)}</span>
    </Nav.Link>
  );

  // カテゴリ（開閉可能）。折りたたみ幅（アイコンのみ）のときはヘッダを隠し、
  // 項目を常に表示する（閉じたカテゴリの項目に到達できなくなるのを防ぐ）。
  const renderCategory = (id: string, label: string, items: NavItem[]) => {
    const visible = items.filter((item) => !item.permission || hasPermission(item.permission));
    if (visible.length === 0) return null;
    const open = openCategories[id] !== false;
    return (
      <React.Fragment key={id}>
        <button
          type="button"
          className="btn btn-link text-decoration-none text-muted text-uppercase fw-bold px-2 mt-3 mb-1 small d-flex align-items-center w-100 sidebar-category-header"
          onClick={(e) => {
            e.stopPropagation();
            toggleCategory(id);
          }}
          aria-expanded={open}
          data-testid={`sidebar-category-${id}`}
        >
          <span className="sidebar-label flex-grow-1 text-start">{t(label)}</span>
          <i className={`fa-solid fa-chevron-${open ? 'down' : 'right'} sidebar-label small`}></i>
        </button>
        {(open || sidebarCollapsed) && visible.map(renderItem)}
      </React.Fragment>
    );
  };

  const navContent = (
    <Nav className="flex-column">
      {renderItem({ to: '/', icon: 'fa-house', label: 'Home' })}
      {hasPermission('dashboard:view') &&
        renderItem({ to: '/dashboard', icon: 'fa-bars-progress', label: 'Dashboard' })}

      {hasPermission('media:view') && (
        <>
          {/* 表示系: 閲覧用のページ */}
          {renderCategory('media', 'Media', [
            { to: '/media', icon: 'fa-images', label: 'Media Gallery' },
            { to: '/albums', icon: 'fa-book', label: 'Albums', permission: 'album:view' },
            { to: '/tags', icon: 'fa-tags', label: 'Tags' },
            { to: '/media/duplicates', icon: 'fa-layer-group', label: 'Duplicates', permission: 'media:delete' },
          ])}

          {/* 取り込み・同期系のページ */}
          {renderCategory('import', 'Import & Sync', [
            { to: '/sessions', icon: 'fa-layer-group', label: 'Sessions', permission: 'media:session' },
            { to: '/jobs', icon: 'fa-list-check', label: 'Sync Jobs', permission: 'media:session' },
            { to: '/photo-imports', icon: 'fa-file-import', label: 'Photo Imports', permission: 'admin:photo-settings' },
            { to: '/photo-settings', icon: 'fa-sliders', label: 'Photo Settings', permission: 'admin:photo-settings' },
          ])}
        </>
      )}

      {renderCategory('admin', 'Administration', [
        { to: '/admin/dashboard', icon: 'fa-server', label: 'System Overview', permission: 'admin:system-settings' },
        { to: '/admin/users', icon: 'fa-users', label: 'Users', permission: 'user:manage' },
        { to: '/admin/roles', icon: 'fa-shield-halved', label: 'Roles', permission: 'user:manage' },
        { to: '/admin/groups', icon: 'fa-sitemap', label: 'Groups', permission: 'user:manage' },
        { to: '/admin/permissions', icon: 'fa-key', label: 'Permissions', permission: 'permission:manage' },
        { to: '/admin/service-accounts', icon: 'fa-robot', label: 'Service Accounts', permission: 'service_account:manage' },
        { to: '/admin/config', icon: 'fa-gear', label: 'System Settings', permission: 'system:manage' },
        { to: '/admin/google-accounts', icon: 'fa-brands fa-google', label: 'Google Accounts', permission: 'admin:system-settings' },
        { to: '/admin/photo-exports', icon: 'fa-file-export', label: 'Photo Exports', permission: 'system:manage' },
      ])}
    </Nav>
  );

  return (
    <>
      {/*
        モバイル(<768px)のドロワー幅は常に一定(labelも常に表示)にし、
        デスクトップ(>=768px)の折りたたみ幅とは完全に切り離す。
        react-bootstrap の Offcanvas は `responsive="md"` で
        <768px: 通常のオフキャンバス（開閉するドロワー）
        >=768px: 静的な通常のサイドバー（常時表示）
        に自動的に切り替わる。
      */}
      <style>{`
        .app-sidebar { --bs-offcanvas-width: 280px; }
        .app-sidebar .sidebar-category-header { font-size: .75rem; }
        .app-sidebar .sidebar-category-header:focus { box-shadow: none; }
        @media (min-width: 768px) {
          .app-sidebar.offcanvas-md { width: 250px; }
          .app-sidebar.offcanvas-md.app-sidebar-collapsed { width: 60px; }
          .app-sidebar.offcanvas-md.app-sidebar-collapsed .sidebar-label { display: none; }
          .app-sidebar.offcanvas-md.app-sidebar-collapsed .sidebar-category-header { display: none; }
        }
      `}</style>
      <Offcanvas
        show={mobileSidebarOpen}
        onHide={() => dispatch(setMobileSidebarOpen(false))}
        responsive="md"
        className={`bg-light border-end app-sidebar ${sidebarCollapsed ? 'app-sidebar-collapsed' : ''}`}
      >
        <Offcanvas.Header closeButton className="d-md-none">
          <Offcanvas.Title>{t('Menu')}</Offcanvas.Title>
        </Offcanvas.Header>
        <Offcanvas.Body className="p-3 d-flex flex-column">
          {navContent}
        </Offcanvas.Body>
      </Offcanvas>
    </>
  );
};

export default Sidebar;

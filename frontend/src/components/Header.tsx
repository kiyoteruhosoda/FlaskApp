import React from 'react';
import { Navbar, Nav, Container, NavDropdown, Button } from 'react-bootstrap';
import { useSelector, useDispatch } from 'react-redux';
import { RootState, AppDispatch } from '../store';
import { logout } from '../store/authSlice';
import { toggleSidebar, toggleMobileSidebar } from '../store/uiSlice';
import { Link, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import ImportActivityBell from './ImportActivityBell';

const Header: React.FC = () => {
  const { t } = useTranslation();
  const dispatch = useDispatch<AppDispatch>();
  const navigate = useNavigate();
  const { user, isAuthenticated } = useSelector((state: RootState) => state.auth);

  const handleLogout = () => {
    dispatch(logout());
    navigate('/login');
  };

  const hasPermission = (permission: string): boolean => {
    return user?.permissions?.includes(permission) || false;
  };

  return (
    <Navbar bg="light" expand="lg" className="border-bottom">
      <Container fluid>
        <div className="d-flex align-items-center">
          {isAuthenticated && (
            <>
              {/* モバイル: オフキャンバスサイドバーの開閉 */}
              <Button
                variant="outline-secondary"
                size="sm"
                className="me-2 d-md-none"
                onClick={() => dispatch(toggleMobileSidebar())}
                aria-label="Toggle navigation"
              >
                <i className="fa-solid fa-bars"></i>
              </Button>
              {/* デスクトップ: サイドバーの折りたたみ */}
              <Button
                variant="outline-secondary"
                size="sm"
                className="me-2 d-none d-md-inline-block"
                onClick={() => dispatch(toggleSidebar())}
                aria-label="Toggle navigation"
              >
                <i className="fa-solid fa-bars"></i>
              </Button>
            </>
          )}
          <Navbar.Brand as={Link} to="/">PhotoNest</Navbar.Brand>
        </div>

        <div className="d-flex align-items-center order-lg-last">
          {/* 実行中の取り込み作業の通知ベル（モバイルでも常時表示） */}
          {isAuthenticated && <ImportActivityBell />}
          {/* 折りたたみメニューのトグル。左のサイドバー開閉（ハンバーガー）と
              区別できるよう、縦三点（ケバブ）アイコンにする。 */}
          <Navbar.Toggle aria-controls="basic-navbar-nav" aria-label="Toggle menu" className="border-0">
            <i className="fa-solid fa-ellipsis-vertical fs-4 px-2"></i>
          </Navbar.Toggle>
        </div>
        <Navbar.Collapse id="basic-navbar-nav">
          {isAuthenticated ? (
            <>
              <Nav className="me-auto">
                <Nav.Link as={Link} to="/">{t('Home')}</Nav.Link>
                {hasPermission('dashboard:view') && (
                  <Nav.Link as={Link} to="/dashboard">{t('Dashboard')}</Nav.Link>
                )}
                {hasPermission('media:view') && (
                  <NavDropdown title={t('Photo View')} id="photo-nav-dropdown">
                    {hasPermission('media:session') && (
                      <NavDropdown.Item as={Link} to="/sessions">{t('Sessions')}</NavDropdown.Item>
                    )}
                    <NavDropdown.Item as={Link} to="/media">{t('Media Gallery')}</NavDropdown.Item>
                    {hasPermission('album:view') && (
                      <NavDropdown.Item as={Link} to="/albums">{t('Albums')}</NavDropdown.Item>
                    )}
                    {hasPermission('admin:photo-settings') && (
                      <>
                        <NavDropdown.Divider />
                        <NavDropdown.Item as={Link} to="/photo-settings">{t('Settings')}</NavDropdown.Item>
                      </>
                    )}
                  </NavDropdown>
                )}
              </Nav>
              <Nav>
                <NavDropdown title={user?.username || 'User'} id="user-nav-dropdown" align="end">
                  <NavDropdown.Item as={Link} to="/profile">{t('Profile')}</NavDropdown.Item>
                  {hasPermission('admin:system-settings') && (
                    <>
                      <NavDropdown.Divider />
                      <NavDropdown.Item as={Link} to="/admin/dashboard">{t('Admin')}</NavDropdown.Item>
                    </>
                  )}
                  <NavDropdown.Divider />
                  <NavDropdown.Item onClick={handleLogout}>{t('Logout')}</NavDropdown.Item>
                </NavDropdown>
              </Nav>
            </>
          ) : (
            <Nav className="ms-auto">
              <Nav.Link as={Link} to="/login">{t('Login')}</Nav.Link>
              <Nav.Link as={Link} to="/register">{t('Register')}</Nav.Link>
            </Nav>
          )}
        </Navbar.Collapse>
      </Container>
    </Navbar>
  );
};

export default Header;
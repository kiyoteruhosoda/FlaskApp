import React from 'react';
import { Navbar, Nav, Container, NavDropdown, Button } from 'react-bootstrap';
import { useSelector, useDispatch } from 'react-redux';
import { RootState, AppDispatch } from '../store';
import { logout } from '../store/authSlice';
import { toggleSidebar } from '../store/uiSlice';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

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
            <Button
              variant="outline-secondary"
              size="sm"
              className="me-2"
              onClick={() => dispatch(toggleSidebar())}
            >
              <i className="bi bi-list"></i>
            </Button>
          )}
          <Navbar.Brand href="/">PhotoNest</Navbar.Brand>
        </div>

        <Navbar.Toggle aria-controls="basic-navbar-nav" />
        <Navbar.Collapse id="basic-navbar-nav">
          {isAuthenticated ? (
            <>
              <Nav className="me-auto">
                <Nav.Link href="/">{t('Home')}</Nav.Link>
                {hasPermission('dashboard:view') && (
                  <Nav.Link href="/dashboard">{t('Dashboard')}</Nav.Link>
                )}
                {hasPermission('media:view') && (
                  <NavDropdown title={t('Photo View')} id="photo-nav-dropdown">
                    {hasPermission('media:session') && (
                      <NavDropdown.Item href="/sessions">{t('Sessions')}</NavDropdown.Item>
                    )}
                    <NavDropdown.Item href="/media">{t('Media Gallery')}</NavDropdown.Item>
                    {hasPermission('album:view') && (
                      <NavDropdown.Item href="/albums">{t('Albums')}</NavDropdown.Item>
                    )}
                    {hasPermission('admin:photo-settings') && (
                      <>
                        <NavDropdown.Divider />
                        <NavDropdown.Item href="/photo-settings">{t('Settings')}</NavDropdown.Item>
                      </>
                    )}
                  </NavDropdown>
                )}
              </Nav>
              <Nav>
                <NavDropdown title={user?.username || 'User'} id="user-nav-dropdown" align="end">
                  <NavDropdown.Item href="/profile">{t('Profile')}</NavDropdown.Item>
                  {hasPermission('admin:system-settings') && (
                    <>
                      <NavDropdown.Divider />
                      <NavDropdown.Item href="/admin">{t('Admin')}</NavDropdown.Item>
                    </>
                  )}
                  <NavDropdown.Divider />
                  <NavDropdown.Item onClick={handleLogout}>{t('Logout')}</NavDropdown.Item>
                </NavDropdown>
              </Nav>
            </>
          ) : (
            <Nav className="ms-auto">
              <Nav.Link href="/login">{t('Login')}</Nav.Link>
              <Nav.Link href="/register">{t('Register')}</Nav.Link>
            </Nav>
          )}
        </Navbar.Collapse>
      </Container>
    </Navbar>
  );
};

export default Header;
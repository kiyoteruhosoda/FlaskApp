import React, { useState } from 'react';
import { Container, Row, Col, Card, Form, Button, Alert, Spinner, Dropdown } from 'react-bootstrap';
import { useNavigate, Link } from 'react-router-dom';
import { useDispatch } from 'react-redux';
import { AppDispatch } from '../store';
import { getCurrentUser } from '../store/authSlice';
import { useTranslation } from 'react-i18next';
import i18n from 'i18next';
import apiClient from '../services/api';

const RegisterPage: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const dispatch = useDispatch<AppDispatch>();

  const changeLanguage = (lng: string) => {
    i18n.changeLanguage(lng);
  };

  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!email.trim()) {
      setError(t('Email is required'));
      return;
    }
    if (!password) {
      setError(t('Password is required'));
      return;
    }
    if (password.length < 8) {
      setError(t('Password must be at least 8 characters'));
      return;
    }
    if (password !== confirmPassword) {
      setError(t('Passwords do not match'));
      return;
    }

    setLoading(true);
    try {
      const res = await apiClient.registerUser({
        email: email.trim(),
        password,
        username: username.trim() || undefined,
      });
      localStorage.setItem('access_token', res.access_token);
      localStorage.setItem('refresh_token', res.refresh_token);
      await dispatch(getCurrentUser());
      navigate('/');
    } catch (err: any) {
      const code = err.response?.data?.error;
      if (code === 'email_exists') {
        setError(t('Email already in use'));
      } else if (code === 'password_too_short') {
        setError(t('Password must be at least 8 characters'));
      } else {
        setError(t('Failed to register'));
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div data-testid="register-page" className="h-100">
      <Container fluid className="h-100 py-4 d-flex align-items-center justify-content-center bg-light">

      <Row className="w-100">
        <Col md={6} lg={4} className="mx-auto">
          <Card className="border-0 bg-transparent">
            <Card.Header className="text-center py-3 border-0 bg-transparent">
              <span className="text-muted">{t('Create an account')}</span>
            </Card.Header>
            <Card.Body className="p-4">
              {error && <Alert variant="danger" data-testid="register-error">{error}</Alert>}

              <Form onSubmit={handleSubmit}>
                <Form.Group className="mb-3">
                  <Form.Label>{t('Email')}</Form.Label>
                  <Form.Control
                    type="email"
                    name="email"
                    value={email}
                    onChange={e => setEmail(e.target.value)}
                    placeholder={t('Enter your email')}
                    autoFocus
                    required
                  />
                </Form.Group>

                <Form.Group className="mb-3">
                  <Form.Label>{t('Username')}</Form.Label>
                  <Form.Control
                    type="text"
                    name="username"
                    value={username}
                    onChange={e => setUsername(e.target.value)}
                    placeholder={t('Enter your username')}
                  />
                </Form.Group>

                <Form.Group className="mb-3">
                  <Form.Label>{t('Password')}</Form.Label>
                  <Form.Control
                    type="password"
                    name="password"
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    placeholder={t('Enter your password')}
                    required
                  />
                </Form.Group>

                <Form.Group className="mb-4">
                  <Form.Label>{t('Confirm Password')}</Form.Label>
                  <Form.Control
                    type="password"
                    name="confirm_password"
                    value={confirmPassword}
                    onChange={e => setConfirmPassword(e.target.value)}
                    placeholder={t('Enter your password again')}
                    required
                  />
                </Form.Group>

                <Button
                  type="submit"
                  variant="primary"
                  className="w-100"
                  disabled={loading}
                  data-testid="register-submit"
                >
                  {loading
                    ? <><Spinner size="sm" className="me-2" />{t('Signing up...')}</>
                    : t('Sign Up')}
                </Button>
              </Form>
            </Card.Body>
            <Card.Footer className="text-center py-3 border-0 bg-transparent">
              <div className="mb-2">
                <small className="text-muted">
                  {t("Already have an account?")}{' '}
                  <Link to="/login" className="text-decoration-none">
                    {t('Sign in here')}
                  </Link>
                </small>
              </div>
              {/* 言語切替 */}
              <Dropdown align="end" className="d-inline-block">
                <Dropdown.Toggle
                  variant="link"
                  size="sm"
                  className="text-decoration-none text-muted p-0"
                >
                  {i18n.language === 'ja' ? '🇯🇵 日本語' : '🇺🇸 English'}
                </Dropdown.Toggle>
                <Dropdown.Menu>
                  <Dropdown.Item onClick={() => changeLanguage('ja')}>🇯🇵 日本語</Dropdown.Item>
                  <Dropdown.Item onClick={() => changeLanguage('en')}>🇺🇸 English</Dropdown.Item>
                </Dropdown.Menu>
              </Dropdown>
            </Card.Footer>
          </Card>
        </Col>
      </Row>
    </Container>
    </div>
  );
};

export default RegisterPage;

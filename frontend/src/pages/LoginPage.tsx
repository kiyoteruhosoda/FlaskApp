import React, { useState, useEffect } from 'react';
import { Container, Row, Col, Card, Form, Button, Alert, Spinner, Dropdown } from 'react-bootstrap';
import { useDispatch, useSelector } from 'react-redux';
import { RootState, AppDispatch } from '../store';
import { login, clearError, getCurrentUser } from '../store/authSlice';
import { useNavigate, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import i18n from 'i18next';
import axios from 'axios';
import { startPasskeyAuthentication, isPasskeySupported } from '../utils/webauthn';

const LoginPage: React.FC = () => {
  const { t } = useTranslation();
  const dispatch = useDispatch<AppDispatch>();
  const navigate = useNavigate();
  const { isLoading, error } = useSelector((state: RootState) => state.auth);

  const [formData, setFormData] = useState({
    email: '',
    password: '',
    totp_code: '',
  });

  const [loginStep, setLoginStep] = useState<'credentials' | 'totp'>('credentials');
  const [passkeyLoading, setPasskeyLoading] = useState(false);
  const [passkeyError, setPasskeyError] = useState<string | null>(null);

  const changeLanguage = (lng: string) => {
    i18n.changeLanguage(lng);
  };

  useEffect(() => {
    return () => {
      dispatch(clearError());
    };
  }, [dispatch]);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value,
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    const loginData = {
      email: formData.email,
      password: formData.password,
      ...(loginStep === 'totp' && formData.totp_code && { token: formData.totp_code }),
    };

    try {
      const result = await dispatch(login(loginData));

      if (login.fulfilled.match(result)) {
        // ログイン成功後、ユーザー情報を取得
        await dispatch(getCurrentUser());

        // ロール選択が必要かチェック
        if (result.payload.requires_role_selection) {
          navigate('/select-role');
        } else {
          // redirect_urlまたはデフォルトのダッシュボードへ
          const redirectUrl = result.payload.redirect_url || '/dashboard';
          navigate(redirectUrl);
        }
      } else if (login.rejected.match(result)) {
        // TOTPが必要な場合は専用画面に切り替える
        const errorMessage = result.payload as string;
        if (errorMessage === 'totp_required') {
          setFormData(prev => ({ ...prev, totp_code: '' }));
          setLoginStep('totp');
        } else if (errorMessage === 'invalid_totp') {
          setFormData(prev => ({ ...prev, totp_code: '' }));
        }
      }
    } catch (error) {
      console.error('Login error:', error);
    }
  };

  const handleBackToCredentials = () => {
    dispatch(clearError());
    setFormData(prev => ({ ...prev, totp_code: '' }));
    setLoginStep('credentials');
  };

  const handlePasskeyLogin = async () => {
    setPasskeyError(null);
    if (!isPasskeySupported()) {
      setPasskeyError(t('Passkey is not supported on this device'));
      return;
    }
    setPasskeyLoading(true);
    try {
      // 認証オプション取得(チャレンジは Flask セッションに保持されるため cookie 必須)
      const optionsRes = await axios.post(
        '/auth/passkey/options/login',
        formData.email ? { email: formData.email } : {},
        { withCredentials: true }
      );
      const assertion = await startPasskeyAuthentication(optionsRes.data);
      const verifyRes = await axios.post('/auth/passkey/verify/login', assertion, {
        withCredentials: true,
      });
      const data = verifyRes.data || {};
      if (data.access_token) localStorage.setItem('access_token', data.access_token);
      if (data.refresh_token) localStorage.setItem('refresh_token', data.refresh_token);

      await dispatch(getCurrentUser());
      if (data.requires_role_selection) {
        navigate('/select-role');
      } else {
        navigate(data.redirect_url || '/dashboard');
      }
    } catch (err: any) {
      if (err?.name === 'NotAllowedError' || err?.message === 'passkey_canceled') {
        setPasskeyError(t('Passkey sign-in was canceled'));
      } else {
        setPasskeyError(
          err?.response?.data?.error || t('Passkey sign-in failed')
        );
      }
    } finally {
      setPasskeyLoading(false);
    }
  };

  return (
    <div data-testid="login-page">
      <Container fluid className="min-vh-100 d-flex align-items-center justify-content-center bg-light">

      <Row className="w-100">
        <Col md={6} lg={4} className="mx-auto">
          <Card className="shadow">
            <Card.Header className="text-center py-3 position-relative">
              {/* 言語切替 - カード内右上 */}
              <div className="position-absolute top-0 end-0 m-2">
                <Dropdown align="end">
                  <Dropdown.Toggle variant="outline-secondary" size="sm" className="border-0">
                    {i18n.language === 'ja' ? '🇯🇵 日本語' : '🇺🇸 English'}
                  </Dropdown.Toggle>
                  <Dropdown.Menu>
                    <Dropdown.Item onClick={() => changeLanguage('ja')}>🇯🇵 日本語</Dropdown.Item>
                    <Dropdown.Item onClick={() => changeLanguage('en')}>🇺🇸 English</Dropdown.Item>
                  </Dropdown.Menu>
                </Dropdown>
              </div>
              <h4 className="mb-0">PhotoNest</h4>
              <small className="text-muted">
                {loginStep === 'totp'
                  ? t('Two-factor authentication')
                  : t('Please sign in to your account')}
              </small>
            </Card.Header>
            <Card.Body className="p-4">
              {error && (
                <Alert variant="danger" dismissible onClose={() => dispatch(clearError())}>
                  {error}
                </Alert>
              )}

              {loginStep === 'credentials' ? (
                <Form onSubmit={handleSubmit}>
                  <Form.Group className="mb-3">
                    <Form.Label>{t('Email')}</Form.Label>
                    <Form.Control
                      type="email"
                      name="email"
                      value={formData.email}
                      onChange={handleInputChange}
                      placeholder={t('Enter your email')}
                      required
                      autoFocus
                    />
                  </Form.Group>

                  <Form.Group className="mb-3">
                    <Form.Label>{t('Password')}</Form.Label>
                    <Form.Control
                      type="password"
                      name="password"
                      value={formData.password}
                      onChange={handleInputChange}
                      placeholder={t('Enter your password')}
                      required
                    />
                  </Form.Group>

                  <Button
                    variant="primary"
                    type="submit"
                    className="w-100 mb-3"
                    disabled={isLoading}
                    data-testid="login-submit"
                  >
                    {isLoading ? (
                      <>
                        <Spinner animation="border" size="sm" className="me-2" />
                        {t('Signing in...')}
                      </>
                    ) : (
                      t('Sign In')
                    )}
                  </Button>

                  {passkeyError && (
                    <Alert variant="warning" dismissible onClose={() => setPasskeyError(null)}>
                      {passkeyError}
                    </Alert>
                  )}

                  {/* パスキーログイン */}
                  <div className="d-grid mb-3">
                    <Button
                      variant="outline-secondary"
                      onClick={handlePasskeyLogin}
                      disabled={passkeyLoading}
                      data-testid="passkey-login-btn"
                    >
                      {passkeyLoading ? (
                        <>
                          <Spinner animation="border" size="sm" className="me-2" />
                          {t('Authenticating...')}
                        </>
                      ) : (
                        <>
                          <i className="fa-solid fa-key me-2" />{t('Sign in with Passkey')}
                        </>
                      )}
                    </Button>
                  </div>

                  <div className="text-center">
                    <Link to="/forgot-password" className="text-decoration-none">
                      {t('Forgot your password?')}
                    </Link>
                  </div>
                </Form>
              ) : (
                <Form onSubmit={handleSubmit} data-testid="totp-step-form">
                  <Form.Group className="mb-3">
                    <Form.Label>{t('Authentication Code')}</Form.Label>
                    <Form.Control
                      type="text"
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      name="totp_code"
                      value={formData.totp_code}
                      onChange={handleInputChange}
                      placeholder={t('Enter 6-digit code')}
                      maxLength={6}
                      required
                      autoFocus
                      data-testid="totp-code-input"
                    />
                    <Form.Text className="text-muted">
                      {t('Enter the 6-digit code from your authenticator app')}
                    </Form.Text>
                  </Form.Group>

                  <Button
                    variant="primary"
                    type="submit"
                    className="w-100 mb-3"
                    disabled={isLoading}
                    data-testid="login-submit"
                  >
                    {isLoading ? (
                      <>
                        <Spinner animation="border" size="sm" className="me-2" />
                        {t('Signing in...')}
                      </>
                    ) : (
                      t('Sign In')
                    )}
                  </Button>

                  <div className="text-center">
                    <Button
                      variant="link"
                      className="text-decoration-none p-0"
                      onClick={handleBackToCredentials}
                      data-testid="totp-back-btn"
                    >
                      {t('Back')}
                    </Button>
                  </div>
                </Form>
              )}
            </Card.Body>
            {loginStep === 'credentials' && (
              <Card.Footer className="text-center py-3">
                <small className="text-muted">
                  {t("Don't have an account?")}{' '}
                  <Link to="/register" className="text-decoration-none">
                    {t('Sign up here')}
                  </Link>
                </small>
              </Card.Footer>
            )}
          </Card>
        </Col>
      </Row>
    </Container>
    </div>
  );
};

export default LoginPage;
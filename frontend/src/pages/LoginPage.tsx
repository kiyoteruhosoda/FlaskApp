import React, { useState, useEffect } from 'react';
import { Container, Row, Col, Card, Form, Button, Alert, Spinner, Dropdown, InputGroup } from 'react-bootstrap';
import { useDispatch, useSelector } from 'react-redux';
import { RootState, AppDispatch } from '../store';
import { login, clearError, getCurrentUser } from '../store/authSlice';
import { useNavigate, Link, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import i18n from 'i18next';
import axios from 'axios';
import { startPasskeyAuthentication, isPasskeySupported } from '../utils/webauthn';
import { localeRoutePolicyOf, type SupportedLocale } from '../i18n/localePath';

const LoginPage: React.FC = () => {
  const { t } = useTranslation();
  const dispatch = useDispatch<AppDispatch>();
  const navigate = useNavigate();
  const location = useLocation();
  const { isLoading, error } = useSelector((state: RootState) => state.auth);

  const [formData, setFormData] = useState({
    email: '',
    password: '',
    totp_code: '',
  });

  const [loginStep, setLoginStep] = useState<'credentials' | 'totp'>('credentials');
  const [passkeyLoading, setPasskeyLoading] = useState(false);
  const [passkeyError, setPasskeyError] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);

  const changeLanguage = (lng: SupportedLocale) => {
    i18n.changeLanguage(lng);
    const target = localeRoutePolicyOf(lng).loginPath;
    if (location.pathname !== target) {
      navigate(target, { replace: true });
    }
  };

  // APIのエラーコードを利用者向けメッセージに変換する。
  // invalid_token・authentication_required 等の内部コードは、ログイン直後の
  // getCurrentUser() が一時的に失敗した際などに state.error へ流れてくることが
  // あるが、利用者には意味が伝わらず不安を煽るだけなので表示しない（null を返す）。
  const errorText = (code: string): string | null => {
    switch (code) {
      case 'invalid_totp':
        return t('Invalid authentication code');
      case 'invalid_credentials':
        return t('Invalid email or password');
      default:
        return null;
    }
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

        // パスワード変更が必要かチェック
        if (result.payload.requires_password_change) {
          navigate('/change-password', { replace: true });
        // ロール選択が必要かチェック
        } else if (result.payload.requires_role_selection) {
          navigate('/select-role');
        } else {
          // redirect_urlまたはデフォルトのダッシュボードへ
          const redirectUrl = result.payload.redirect_url || '/dashboard';
          navigate(redirectUrl);
        }
      } else if (login.rejected.match(result)) {
        // TOTPが必要な場合はエラーではなく通常の案内として専用画面に切り替える
        const errorMessage = result.payload as string;
        if (errorMessage === 'totp_required') {
          dispatch(clearError());
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
    } catch {
      if (!isPasskeySupported()) {
        setPasskeyError(t('Passkey is not supported on this device'));
      } else {
        // キャンセル・未登録・認証失敗など、深刻ではない失敗はすべて
        // 「パスキーが登録されていません」という簡潔な案内に統一する
        setPasskeyError(t('No passkeys registered'));
      }
    } finally {
      setPasskeyLoading(false);
    }
  };

  return (
    // flex-grow + my-auto で「収まるときはスクロールなしで縦中央」「収まらない
    // ときだけ自然にスクロール」を実現する（固定高さ h-100 は使わない）。
    <div
      data-testid="login-page"
      className="flex-grow-1 d-flex flex-column bg-white"
      // 既定の --bs-border-color (#dee2e6) は薄いため、ログイン画面のフォーム枠線を
      // #6c757d に濃くする。パスワード表示ボタン(outline-secondary)の枠線色と揃う。
      style={{ '--bs-border-color': '#6c757d' } as React.CSSProperties}
    >
      <Container fluid className="my-auto py-4 d-flex align-items-center justify-content-center">

      <Row className="w-100">
        <Col md={6} lg={4} className="mx-auto">
          <Card className="border-0 bg-transparent">
            <Card.Header className="text-center py-3 border-0 bg-transparent">
              <span className="text-muted">
                {loginStep === 'totp'
                  ? t('Two-factor authentication')
                  : t('Please sign in to your account')}
              </span>
            </Card.Header>
            <Card.Body className="p-4">
              {error && errorText(error) && (
                <Alert variant="warning" dismissible onClose={() => dispatch(clearError())}>
                  {errorText(error)}
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
                    <InputGroup>
                      <Form.Control
                        type={showPassword ? 'text' : 'password'}
                        name="password"
                        value={formData.password}
                        onChange={handleInputChange}
                        placeholder={t('Enter your password')}
                        required
                      />
                      <Button
                        variant="outline-secondary"
                        type="button"
                        onClick={() => setShowPassword((prev) => !prev)}
                        aria-label={showPassword ? t('Hide password') : t('Show password')}
                        data-testid="toggle-password-visibility"
                      >
                        <i className={`fa-solid ${showPassword ? 'fa-eye-slash' : 'fa-eye'}`} />
                      </Button>
                    </InputGroup>
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
                    <p className="text-muted small text-center mb-3" data-testid="passkey-error">
                      {passkeyError}
                    </p>
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
                  {/* TOTP要求はエラーではないため通常の案内として表示する */}
                  <Alert variant="info" data-testid="totp-info-message">
                    {t('Enter the authentication code to complete sign-in')}
                  </Alert>
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
            <Card.Footer className="text-center py-3 border-0 bg-transparent">
              {loginStep === 'credentials' && (
                <div className="mb-2">
                  <small className="text-muted">
                    {t("Don't have an account?")}{' '}
                    <Link to="/register" className="text-decoration-none">
                      {t('Sign up here')}
                    </Link>
                  </small>
                </div>
              )}
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

export default LoginPage;
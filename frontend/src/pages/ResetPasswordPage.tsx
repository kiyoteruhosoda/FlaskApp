import React, { useState } from 'react';
import { Container, Card, Form, Button, Alert, Spinner } from 'react-bootstrap';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import apiClient from '../services/api';
import { getApiErrorCode } from '../services/apiErrors';

const ResetPasswordPage: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') || '';

  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
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
    if (!token) {
      setError(t('Invalid or expired reset token'));
      return;
    }
    setLoading(true);
    try {
      await apiClient.resetPassword(token, password);
      navigate('/login', { state: { message: t('Password reset successfully. Please sign in.') } });
    } catch (err: any) {
      const code = getApiErrorCode(err);
      if (code === 'invalid_token') {
        setError(t('Invalid or expired reset token'));
      } else if (code === 'password_too_short') {
        setError(t('Password must be at least 8 characters'));
      } else {
        setError(t('Failed to reset password'));
      }
    } finally {
      setLoading(false);
    }
  };

  if (!token) {
    return (
      <Container
        className="d-flex justify-content-center align-items-center"
        style={{ minHeight: '80vh' }}
        data-testid="reset-password-page"
      >
        <Card style={{ width: '100%', maxWidth: 420 }}>
          <Card.Body className="p-4">
            <Alert variant="danger">{t('Invalid or expired reset token')}</Alert>
            <p className="text-center mb-0 small">
              <Link to="/forgot-password">{t('Request a new reset link')}</Link>
            </p>
          </Card.Body>
        </Card>
      </Container>
    );
  }

  return (
    <Container
      className="d-flex justify-content-center align-items-center"
      style={{ minHeight: '80vh' }}
      data-testid="reset-password-page"
    >
      <Card style={{ width: '100%', maxWidth: 420 }}>
        <Card.Body className="p-4">
          <h4 className="mb-4 text-center">{t('Reset Password')}</h4>

          {error && <Alert variant="danger" data-testid="reset-password-error">{error}</Alert>}

          <Form onSubmit={handleSubmit}>
            <Form.Group className="mb-3">
              <Form.Label>{t('New Password')}</Form.Label>
              <Form.Control
                type="password"
                name="new_password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={t('Enter your password')}
                autoFocus
                required
              />
            </Form.Group>

            <Form.Group className="mb-4">
              <Form.Label>{t('Confirm Password')}</Form.Label>
              <Form.Control
                type="password"
                name="confirm_password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder={t('Enter your password again')}
                required
              />
            </Form.Group>

            <Button
              type="submit"
              variant="primary"
              className="w-100"
              disabled={loading}
              data-testid="reset-password-submit"
            >
              {loading
                ? <><Spinner size="sm" className="me-2" />{t('Resetting...')}</>
                : t('Reset Password')}
            </Button>
          </Form>

          <hr />
          <p className="text-center mb-0 small">
            <Link to="/login">{t('Back to Login')}</Link>
          </p>
        </Card.Body>
      </Card>
    </Container>
  );
};

export default ResetPasswordPage;

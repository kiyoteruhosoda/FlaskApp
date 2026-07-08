import React, { useState } from 'react';
import { Container, Card, Form, Button, Alert, Spinner } from 'react-bootstrap';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import apiClient from '../services/api';

const ChangePasswordPage: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();

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

    setLoading(true);
    try {
      await apiClient.forceChangePassword(password);
      navigate('/dashboard', { replace: true });
    } catch (err: any) {
      const code = err.response?.data?.error;
      if (code === 'password_too_short') {
        setError(t('Password must be at least 8 characters'));
      } else if (code === 'invalid_current_password') {
        setError(t('Current password is incorrect'));
      } else {
        setError(t('Failed to change password'));
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <Container
      className="d-flex justify-content-center align-items-center"
      style={{ minHeight: '80vh' }}
      data-testid="change-password-page"
    >
      <Card style={{ width: '100%', maxWidth: 420 }}>
        <Card.Body className="p-4">
          <h4 className="mb-2 text-center">{t('Change Password Required')}</h4>
          <p className="text-muted text-center small mb-4">
            {t('Your password must be changed before continuing.')}
          </p>

          {error && <Alert variant="danger" data-testid="change-password-error">{error}</Alert>}

          <Form onSubmit={handleSubmit}>
            <Form.Group className="mb-3">
              <Form.Label>{t('New Password')}</Form.Label>
              <Form.Control
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={t('Enter new password')}
                autoFocus
                required
                data-testid="change-password-new"
              />
            </Form.Group>

            <Form.Group className="mb-4">
              <Form.Label>{t('Confirm Password')}</Form.Label>
              <Form.Control
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder={t('Confirm new password')}
                required
                data-testid="change-password-confirm"
              />
            </Form.Group>

            <Button
              type="submit"
              variant="primary"
              className="w-100"
              disabled={loading}
              data-testid="change-password-submit"
            >
              {loading
                ? <><Spinner size="sm" className="me-2" />{t('Saving...')}</>
                : t('Change Password')}
            </Button>
          </Form>
        </Card.Body>
      </Card>
    </Container>
  );
};

export default ChangePasswordPage;

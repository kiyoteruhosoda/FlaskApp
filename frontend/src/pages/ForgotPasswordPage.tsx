import React, { useState } from 'react';
import { Container, Card, Form, Button, Alert, Spinner } from 'react-bootstrap';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import apiClient from '../services/api';
import { getApiErrorCode } from '../services/apiErrors';

const ForgotPasswordPage: React.FC = () => {
  const { t } = useTranslation();
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (!email.trim()) {
      setError(t('Email is required'));
      return;
    }
    setLoading(true);
    try {
      await apiClient.forgotPassword(email.trim());
      setSent(true);
    } catch (err: any) {
      const code = getApiErrorCode(err);
      if (code === 'mail_disabled') {
        setError(err.response?.data?.message || t('Mail service not configured'));
      } else {
        setError(t('Failed to send reset email'));
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <Container
      className="d-flex justify-content-center align-items-center"
      style={{ minHeight: '80vh' }}
      data-testid="forgot-password-page"
    >
      <Card style={{ width: '100%', maxWidth: 420 }}>
        <Card.Body className="p-4">
          <h4 className="mb-4 text-center">{t('Forgot Password')}</h4>

          {sent ? (
            <Alert variant="success" data-testid="forgot-password-success">
              {t('Reset link sent. Check your email.')}
            </Alert>
          ) : (
            <>
              <p className="text-muted small mb-3">{t('Enter your email to receive a reset link')}</p>
              {error && <Alert variant="danger" data-testid="forgot-password-error">{error}</Alert>}
              <Form onSubmit={handleSubmit}>
                <Form.Group className="mb-3">
                  <Form.Label>{t('Email')}</Form.Label>
                  <Form.Control
                    type="email"
                    name="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder={t('Enter your email')}
                    autoFocus
                    required
                  />
                </Form.Group>
                <Button
                  type="submit"
                  variant="primary"
                  className="w-100"
                  disabled={loading}
                  data-testid="forgot-password-submit"
                >
                  {loading
                    ? <><Spinner size="sm" className="me-2" />{t('Sending...')}</>
                    : t('Send Reset Email')}
                </Button>
              </Form>
            </>
          )}

          <hr />
          <p className="text-center mb-0 small">
            <Link to="/login">{t('Back to Login')}</Link>
          </p>
        </Card.Body>
      </Card>
    </Container>
  );
};

export default ForgotPasswordPage;

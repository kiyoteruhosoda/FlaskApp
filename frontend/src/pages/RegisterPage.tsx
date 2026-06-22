import React, { useState } from 'react';
import { Container, Card, Form, Button, Alert, Spinner } from 'react-bootstrap';
import { useNavigate, Link } from 'react-router-dom';
import { useDispatch } from 'react-redux';
import { AppDispatch } from '../store';
import { getCurrentUser } from '../store/authSlice';
import { useTranslation } from 'react-i18next';
import apiClient from '../services/api';

const RegisterPage: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const dispatch = useDispatch<AppDispatch>();

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
    <Container
      className="d-flex justify-content-center align-items-center"
      style={{ minHeight: '80vh' }}
    >
      <Card style={{ width: '100%', maxWidth: 420 }}>
        <Card.Body className="p-4">
          <h4 className="mb-4 text-center">{t('Create an account')}</h4>

          {error && <Alert variant="danger">{error}</Alert>}

          <Form onSubmit={handleSubmit}>
            <Form.Group className="mb-3">
              <Form.Label>{t('Email')}</Form.Label>
              <Form.Control
                type="email"
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
                value={username}
                onChange={e => setUsername(e.target.value)}
                placeholder={t('Enter your username')}
              />
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Label>{t('Password')}</Form.Label>
              <Form.Control
                type="password"
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
            >
              {loading
                ? <><Spinner size="sm" className="me-2" />{t('Signing up...')}</>
                : t('Sign Up')}
            </Button>
          </Form>

          <hr />
          <p className="text-center mb-0 small">
            {t("Already have an account?")}{' '}
            <Link to="/login">{t('Sign in here')}</Link>
          </p>
        </Card.Body>
      </Card>
    </Container>
  );
};

export default RegisterPage;

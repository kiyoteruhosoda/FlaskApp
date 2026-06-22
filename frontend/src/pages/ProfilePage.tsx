import React, { useState, useEffect } from 'react';
import { Container, Card, Row, Col, Button, Form, Alert, Badge, Spinner } from 'react-bootstrap';
import { useSelector, useDispatch } from 'react-redux';
import { RootState, AppDispatch } from '../store';
import { getCurrentUser } from '../store/authSlice';
import { useTranslation } from 'react-i18next';
import { TOTPSetupResponse } from '../types/api';
import apiClient from '../services/api';

const ProfilePage: React.FC = () => {
  const { t } = useTranslation();
  const dispatch = useDispatch<AppDispatch>();
  const { user } = useSelector((state: RootState) => state.auth);

  // Profile edit state
  const [editMode, setEditMode] = useState(false);
  const [editEmail, setEditEmail] = useState('');
  const [editUsername, setEditUsername] = useState('');
  const [editPassword, setEditPassword] = useState('');
  const [editConfirmPassword, setEditConfirmPassword] = useState('');
  const [editError, setEditError] = useState('');
  const [editSuccess, setEditSuccess] = useState(false);
  const [saving, setSaving] = useState(false);

  // 2FA state
  const [totpEnabled, setTotpEnabled] = useState<boolean | null>(null);
  const [totpLoading, setTotpLoading] = useState(true);
  const [totpSetupData, setTotpSetupData] = useState<TOTPSetupResponse | null>(null);
  const [totpCode, setTotpCode] = useState('');
  const [totpError, setTotpError] = useState('');
  const [totpBusy, setTotpBusy] = useState(false);
  const [totpSuccess, setTotpSuccess] = useState('');
  const [showDisableConfirm, setShowDisableConfirm] = useState(false);

  useEffect(() => {
    loadTOTPStatus();
  }, []);

  const loadTOTPStatus = async () => {
    setTotpLoading(true);
    try {
      const res = await apiClient.getTOTPStatus();
      setTotpEnabled(res.enabled);
    } catch {
      setTotpEnabled(null);
    } finally {
      setTotpLoading(false);
    }
  };

  const startEdit = () => {
    setEditEmail(user?.email || '');
    setEditUsername(user?.username || '');
    setEditPassword('');
    setEditConfirmPassword('');
    setEditError('');
    setEditSuccess(false);
    setEditMode(true);
  };

  const cancelEdit = () => {
    setEditMode(false);
    setEditError('');
    setEditSuccess(false);
  };

  const handleSaveProfile = async () => {
    setEditError('');
    if (!editEmail.trim()) {
      setEditError(t('Email is required'));
      return;
    }
    if (editPassword && editPassword !== editConfirmPassword) {
      setEditError(t('Passwords do not match'));
      return;
    }
    if (editPassword && editPassword.length < 8) {
      setEditError(t('Password must be at least 8 characters'));
      return;
    }

    setSaving(true);
    try {
      const payload: { email?: string; username?: string; password?: string } = {};
      if (editEmail !== user?.email) payload.email = editEmail;
      if (editUsername !== (user?.username || '')) payload.username = editUsername;
      if (editPassword) payload.password = editPassword;

      await apiClient.updateUserProfile(payload);
      await dispatch(getCurrentUser());
      setEditSuccess(true);
      setEditMode(false);
      setEditPassword('');
      setEditConfirmPassword('');
    } catch (err: any) {
      const code = err.response?.data?.error;
      if (code === 'email_exists') {
        setEditError(t('Email already in use'));
      } else {
        setEditError(t('Failed to update profile'));
      }
    } finally {
      setSaving(false);
    }
  };

  const handleSetupTOTP = async () => {
    setTotpError('');
    setTotpSuccess('');
    setTotpBusy(true);
    try {
      const data = await apiClient.setupTOTP();
      setTotpSetupData(data);
      setTotpCode('');
    } catch {
      setTotpError(t('Failed to enable 2FA'));
    } finally {
      setTotpBusy(false);
    }
  };

  const handleConfirmTOTP = async () => {
    if (!totpSetupData) return;
    setTotpError('');
    setTotpBusy(true);
    try {
      await apiClient.confirmTOTP(totpSetupData.secret, totpCode);
      setTotpEnabled(true);
      setTotpSetupData(null);
      setTotpCode('');
      setTotpSuccess(t('2FA enabled successfully'));
    } catch (err: any) {
      const code = err.response?.data?.error;
      if (code === 'invalid_code') {
        setTotpError(t('Invalid verification code'));
      } else {
        setTotpError(t('Failed to enable 2FA'));
      }
    } finally {
      setTotpBusy(false);
    }
  };

  const handleCancelSetup = () => {
    setTotpSetupData(null);
    setTotpCode('');
    setTotpError('');
  };

  const handleDisableTOTP = async () => {
    setTotpError('');
    setTotpSuccess('');
    setTotpBusy(true);
    try {
      await apiClient.disableTOTP();
      setTotpEnabled(false);
      setShowDisableConfirm(false);
      setTotpSuccess(t('2FA disabled successfully'));
    } catch {
      setTotpError(t('Failed to disable 2FA'));
    } finally {
      setTotpBusy(false);
    }
  };

  if (!user) return null;

  return (
    <Container className="py-4" style={{ maxWidth: 700 }}>
      <h2 className="mb-4">{t('Profile')}</h2>

      {/* Profile Info Card */}
      <Card className="mb-4">
        <Card.Body>
          <div className="d-flex justify-content-between align-items-start mb-3">
            <Card.Title className="mb-0">{t('Profile')}</Card.Title>
            {!editMode && (
              <Button variant="outline-primary" size="sm" onClick={startEdit}>
                <i className="bi bi-pencil me-1"></i>{t('Edit')}
              </Button>
            )}
          </div>

          {editSuccess && !editMode && (
            <Alert variant="success" dismissible onClose={() => setEditSuccess(false)}>
              {t('Profile updated successfully')}
            </Alert>
          )}

          {!editMode ? (
            <Row>
              <Col sm={3} className="text-muted fw-semibold mb-2">{t('Email')}</Col>
              <Col sm={9} className="mb-2">{user.email}</Col>
              <Col sm={3} className="text-muted fw-semibold mb-2">{t('Username')}</Col>
              <Col sm={9} className="mb-2">{user.username || <span className="text-muted">—</span>}</Col>
              {user.created_at && (
                <>
                  <Col sm={3} className="text-muted fw-semibold mb-2">{t('Member since')}</Col>
                  <Col sm={9} className="mb-2">
                    {new Date(user.created_at).toLocaleDateString()}
                  </Col>
                </>
              )}
            </Row>
          ) : (
            <Form>
              {editError && <Alert variant="danger">{editError}</Alert>}
              <Form.Group className="mb-3">
                <Form.Label>{t('Email')}</Form.Label>
                <Form.Control
                  type="email"
                  value={editEmail}
                  onChange={e => setEditEmail(e.target.value)}
                />
              </Form.Group>
              <Form.Group className="mb-3">
                <Form.Label>{t('Username')}</Form.Label>
                <Form.Control
                  type="text"
                  value={editUsername}
                  onChange={e => setEditUsername(e.target.value)}
                  placeholder={t('Enter your username')}
                />
              </Form.Group>
              <hr />
              <p className="text-muted small">{t('Leave blank to keep current password')}</p>
              <Form.Group className="mb-3">
                <Form.Label>{t('New Password')}</Form.Label>
                <Form.Control
                  type="password"
                  value={editPassword}
                  onChange={e => setEditPassword(e.target.value)}
                  placeholder={t('New Password')}
                />
              </Form.Group>
              <Form.Group className="mb-3">
                <Form.Label>{t('Confirm Password')}</Form.Label>
                <Form.Control
                  type="password"
                  value={editConfirmPassword}
                  onChange={e => setEditConfirmPassword(e.target.value)}
                  placeholder={t('Confirm Password')}
                />
              </Form.Group>
              <div className="d-flex gap-2">
                <Button variant="primary" onClick={handleSaveProfile} disabled={saving}>
                  {saving ? <><Spinner size="sm" className="me-1" />{t('Saving...')}</> : t('Save')}
                </Button>
                <Button variant="outline-secondary" onClick={cancelEdit} disabled={saving}>
                  {t('Cancel')}
                </Button>
              </div>
            </Form>
          )}
        </Card.Body>
      </Card>

      {/* Security / 2FA Card */}
      <Card>
        <Card.Body>
          <Card.Title className="mb-3">{t('Security')}</Card.Title>

          <div className="d-flex justify-content-between align-items-center mb-3">
            <div>
              <div className="fw-semibold">{t('Two-Factor Authentication')}</div>
              {totpLoading ? (
                <Spinner size="sm" />
              ) : totpEnabled === null ? (
                <small className="text-muted">{t('Failed to load 2FA status')}</small>
              ) : totpEnabled ? (
                <Badge bg="success">{t('2FA is enabled')}</Badge>
              ) : (
                <Badge bg="secondary">{t('2FA is not enabled')}</Badge>
              )}
            </div>
            {!totpLoading && totpEnabled === false && !totpSetupData && (
              <Button variant="outline-success" size="sm" onClick={handleSetupTOTP} disabled={totpBusy}>
                {totpBusy ? <Spinner size="sm" /> : <><i className="bi bi-shield-lock me-1"></i>{t('Enable 2FA')}</>}
              </Button>
            )}
            {!totpLoading && totpEnabled === true && !showDisableConfirm && (
              <Button variant="outline-danger" size="sm" onClick={() => setShowDisableConfirm(true)} disabled={totpBusy}>
                <i className="bi bi-shield-x me-1"></i>{t('Disable 2FA')}
              </Button>
            )}
          </div>

          {totpSuccess && (
            <Alert variant="success" dismissible onClose={() => setTotpSuccess('')}>
              {totpSuccess}
            </Alert>
          )}
          {totpError && !totpSetupData && (
            <Alert variant="danger" dismissible onClose={() => setTotpError('')}>
              {totpError}
            </Alert>
          )}

          {/* Disable confirmation */}
          {showDisableConfirm && (
            <Alert variant="warning">
              <div className="mb-2">{t('Disable 2FA?')}</div>
              <div className="d-flex gap-2">
                <Button
                  variant="danger"
                  size="sm"
                  onClick={handleDisableTOTP}
                  disabled={totpBusy}
                >
                  {totpBusy ? <Spinner size="sm" /> : t('Disable 2FA')}
                </Button>
                <Button
                  variant="outline-secondary"
                  size="sm"
                  onClick={() => setShowDisableConfirm(false)}
                  disabled={totpBusy}
                >
                  {t('Cancel')}
                </Button>
              </div>
            </Alert>
          )}

          {/* TOTP Setup panel */}
          {totpSetupData && (
            <div className="border rounded p-3 bg-light">
              <p className="mb-3">{t('Scan this QR code with your authenticator app')}</p>
              <div className="text-center mb-3">
                <img
                  src={totpSetupData.qr_data_uri}
                  alt="QR Code"
                  style={{ maxWidth: 200 }}
                />
              </div>
              <div className="mb-3">
                <small className="text-muted d-block mb-1">{t('Or enter this key manually')}</small>
                <code className="user-select-all">{totpSetupData.secret}</code>
              </div>
              {totpError && (
                <Alert variant="danger" dismissible onClose={() => setTotpError('')}>
                  {totpError}
                </Alert>
              )}
              <Form.Group className="mb-3">
                <Form.Label>{t('Enter the 6-digit verification code')}</Form.Label>
                <Form.Control
                  type="text"
                  inputMode="numeric"
                  maxLength={6}
                  value={totpCode}
                  onChange={e => setTotpCode(e.target.value.replace(/\D/g, ''))}
                  placeholder={t('Enter 6-digit code')}
                  style={{ maxWidth: 200 }}
                />
              </Form.Group>
              <div className="d-flex gap-2">
                <Button
                  variant="success"
                  size="sm"
                  onClick={handleConfirmTOTP}
                  disabled={totpBusy || totpCode.length !== 6}
                >
                  {totpBusy ? <Spinner size="sm" /> : t('Verify')}
                </Button>
                <Button
                  variant="outline-secondary"
                  size="sm"
                  onClick={handleCancelSetup}
                  disabled={totpBusy}
                >
                  {t('Cancel')}
                </Button>
              </div>
            </div>
          )}
        </Card.Body>
      </Card>
    </Container>
  );
};

export default ProfilePage;

import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Badge, Button, Card, ListGroup, Modal, Spinner } from 'react-bootstrap';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../services/api';
import { LinkedGoogleAccount } from '../types/api';
import { googleLinkErrorText, useGoogleLinkResult } from '../utils/googleLinkResult';

// プロフィール画面向けの「自分の Google アカウント連携」セクション。
// アカウント登録（OAuth リンク開始）・一覧・連携解除ができる。
const GoogleAccountLinkSection: React.FC = () => {
  const { t } = useTranslation();

  const [accounts, setAccounts] = useState<LinkedGoogleAccount[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [linking, setLinking] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<LinkedGoogleAccount | null>(null);
  const [deleting, setDeleting] = useState(false);

  // OAuth コールバックからの結果（?google_link=...）を表示する
  const linkResult = useGoogleLinkResult();
  const [resultDismissed, setResultDismissed] = useState(false);

  const loadAccounts = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiClient.getLinkedGoogleAccounts({ mine: true });
      setAccounts(data.items || []);
    } catch (e: any) {
      setError(e?.response?.data?.error || e?.message || t('Failed to load Google accounts'));
    } finally {
      setIsLoading(false);
    }
  }, [t]);

  useEffect(() => {
    loadAccounts();
  }, [loadAccounts]);

  const handleLink = async () => {
    setLinking(true);
    setError(null);
    try {
      const res = await apiClient.startGoogleAccountLink('/profile');
      if (res.auth_url) {
        window.location.href = res.auth_url;
      } else {
        setError(t('Failed to start Google authorization'));
      }
    } catch (e: any) {
      setError(e?.response?.data?.error || e?.message || t('Failed to start Google authorization'));
    } finally {
      setLinking(false);
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    setError(null);
    try {
      await apiClient.unlinkGoogleAccount(deleteTarget.id);
      setAccounts((prev) => prev.filter((a) => a.id !== deleteTarget.id));
      setDeleteTarget(null);
    } catch (e: any) {
      setError(e?.response?.data?.error || e?.message || t('Failed to unlink Google account'));
    } finally {
      setDeleting(false);
    }
  };

  return (
    <Card className="mt-4" data-testid="google-account-link-section" id="google-accounts">
      <Card.Body>
        <div className="d-flex justify-content-between align-items-center mb-3">
          <Card.Title className="mb-0">
            <i className="fa-brands fa-google me-2" />
            {t('Google Account Link')}
          </Card.Title>
          <Button
            variant="primary"
            size="sm"
            onClick={handleLink}
            disabled={linking}
            data-testid="profile-google-link-btn"
          >
            {linking ? (
              <><Spinner size="sm" animation="border" className="me-1" />{t('Redirecting...')}</>
            ) : (
              <><i className="fa-solid fa-plus me-1" />{t('Link Google Account')}</>
            )}
          </Button>
        </div>
        <p className="text-muted small">
          {t('Link a Google account to import photos and videos from Google Photos.')}
        </p>

        {linkResult && !resultDismissed && (
          <Alert
            variant={linkResult.result === 'ok' ? 'success' : 'danger'}
            dismissible
            onClose={() => setResultDismissed(true)}
            data-testid="google-link-result"
          >
            {linkResult.result === 'ok'
              ? t('Google account linked: {{email}}', { email: linkResult.email || '' })
              : googleLinkErrorText(linkResult.reason, t)}
          </Alert>
        )}

        {error && (
          <Alert variant="danger" dismissible onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        {isLoading && accounts.length === 0 ? (
          <div className="text-center py-3"><Spinner animation="border" size="sm" /></div>
        ) : accounts.length === 0 ? (
          <div className="text-muted small" data-testid="profile-google-empty">
            {t('No Google accounts linked yet')}
          </div>
        ) : (
          <ListGroup variant="flush" data-testid="profile-google-accounts">
            {accounts.map((account) => (
              <ListGroup.Item key={account.id} className="d-flex justify-content-between align-items-center px-0">
                <div>
                  <span className="fw-semibold">{account.email}</span>
                  <Badge
                    bg={account.status === 'active' ? 'success' : 'secondary'}
                    className="ms-2"
                  >
                    {account.status === 'active' ? t('Active') : t('Disabled')}
                  </Badge>
                  {!account.has_token && (
                    <Badge bg="danger" className="ms-2">{t('Re-authorization required')}</Badge>
                  )}
                </div>
                <Button
                  variant="outline-danger"
                  size="sm"
                  onClick={() => setDeleteTarget(account)}
                  data-testid="profile-google-unlink"
                >
                  <i className="fa-solid fa-link-slash me-1" />{t('Unlink')}
                </Button>
              </ListGroup.Item>
            ))}
          </ListGroup>
        )}
      </Card.Body>

      {/* Unlink confirm */}
      <Modal show={!!deleteTarget} onHide={() => setDeleteTarget(null)} centered>
        <Modal.Header closeButton>
          <Modal.Title>{t('Unlink Google Account')}</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {t('Unlink Google account "{{email}}"? The refresh token will be revoked.', {
            email: deleteTarget?.email,
          })}
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setDeleteTarget(null)}>{t('Cancel')}</Button>
          <Button variant="danger" onClick={confirmDelete} disabled={deleting}>
            {deleting ? <Spinner size="sm" animation="border" /> : t('Unlink')}
          </Button>
        </Modal.Footer>
      </Modal>
    </Card>
  );
};

export default GoogleAccountLinkSection;

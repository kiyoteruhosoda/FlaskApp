import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Container,
  Modal,
  Row,
  Spinner,
  Table,
} from 'react-bootstrap';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../services/api';
import { LinkedGoogleAccount } from '../types/api';
import { formatDateTime } from '../utils/format';
import { googleLinkErrorText, useGoogleLinkResult } from '../utils/googleLinkResult';
import { getApiErrorCode } from '../services/apiErrors';

// Google アカウント連携ページ:
// - アカウント登録（OAuth リンク開始）
// - 連携済みアカウントの一覧・有効/無効切替・接続テスト・解除
const GoogleAccountsPage: React.FC = () => {
  const { t } = useTranslation();

  const [accounts, setAccounts] = useState<LinkedGoogleAccount[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [linking, setLinking] = useState(false);
  const [busyAccountId, setBusyAccountId] = useState<number | null>(null);
  const [testResult, setTestResult] = useState<{ id: number; ok: boolean; message?: string } | null>(null);

  const [deleteTarget, setDeleteTarget] = useState<LinkedGoogleAccount | null>(null);
  const [deleting, setDeleting] = useState(false);

  // OAuth コールバックからの結果（?google_link=...）を表示する
  const linkResult = useGoogleLinkResult();
  const [resultDismissed, setResultDismissed] = useState(false);

  const loadAccounts = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiClient.getLinkedGoogleAccounts();
      setAccounts(data.items || []);
    } catch (e: any) {
      setError(getApiErrorCode(e) || e?.message || t('Failed to load Google accounts'));
    } finally {
      setIsLoading(false);
    }
  }, [t]);

  useEffect(() => {
    loadAccounts();
  }, [loadAccounts]);

  // Google アカウント登録: OAuth 認可 URL を取得して遷移する。
  // 認可完了後はバックエンドのコールバックが redirect で本ページに戻す。
  const handleLink = async () => {
    setLinking(true);
    setError(null);
    try {
      const res = await apiClient.startGoogleAccountLink('/admin/google-accounts');
      if (res.auth_url) {
        window.location.href = res.auth_url;
      } else {
        setError(t('Failed to start Google authorization'));
      }
    } catch (e: any) {
      const code = getApiErrorCode(e);
      setError(
        code === 'encryption_key_not_configured'
          ? t('Token encryption key is not configured. Set it in System Settings > Security & Signing.')
          : e?.response?.data?.message || code || e?.message || t('Failed to start Google authorization')
      );
    } finally {
      setLinking(false);
    }
  };

  const handleToggleStatus = async (account: LinkedGoogleAccount) => {
    const next = account.status === 'active' ? 'disabled' : 'active';
    setBusyAccountId(account.id);
    setError(null);
    try {
      await apiClient.updateGoogleAccountStatus(account.id, next);
      setAccounts((prev) => prev.map((a) => (a.id === account.id ? { ...a, status: next } : a)));
    } catch (e: any) {
      setError(getApiErrorCode(e) || e?.message || t('Failed to update account status'));
    } finally {
      setBusyAccountId(null);
    }
  };

  const handleTest = async (account: LinkedGoogleAccount) => {
    setBusyAccountId(account.id);
    setTestResult(null);
    setError(null);
    try {
      await apiClient.testGoogleAccount(account.id);
      setTestResult({ id: account.id, ok: true });
    } catch (e: any) {
      setTestResult({
        id: account.id,
        ok: false,
        message: getApiErrorCode(e) || e?.message,
      });
    } finally {
      setBusyAccountId(null);
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    setError(null);
    try {
      await apiClient.unlinkGoogleAccount(deleteTarget.id);
      setAccounts((prev) => prev.filter((a) => a.id !== deleteTarget.id));
      setNotice(t('Google account unlinked: {{email}}', { email: deleteTarget.email }));
      setDeleteTarget(null);
    } catch (e: any) {
      setError(getApiErrorCode(e) || e?.message || t('Failed to unlink Google account'));
    } finally {
      setDeleting(false);
    }
  };

  return (
    <Container fluid className="py-4" data-testid="google-accounts-page">
      <Row className="mb-4 align-items-center">
        <Col>
          <h1 className="h3 mb-1">{t('Google Accounts')}</h1>
          <p className="text-muted mb-0">
            {t('Link Google accounts and manage integration settings')}
          </p>
        </Col>
        <Col xs="auto" className="d-flex gap-2">
          <Button
            variant="outline-secondary"
            size="sm"
            onClick={loadAccounts}
            disabled={isLoading}
          >
            <i className="fa-solid fa-rotate-right me-1" />
            {t('Refresh')}
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={handleLink}
            disabled={linking}
            data-testid="google-link-btn"
          >
            {linking ? (
              <><Spinner size="sm" animation="border" className="me-1" />{t('Redirecting...')}</>
            ) : (
              <><i className="fa-brands fa-google me-1" />{t('Link Google Account')}</>
            )}
          </Button>
        </Col>
      </Row>

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
      {notice && (
        <Alert variant="success" dismissible onClose={() => setNotice(null)}>
          {notice}
        </Alert>
      )}

      <Card>
        <Card.Header className="fw-semibold">{t('Linked Accounts')}</Card.Header>
        <Card.Body className="p-0">
          {isLoading && accounts.length === 0 ? (
            <div className="text-center py-5"><Spinner animation="border" /></div>
          ) : accounts.length === 0 ? (
            <div className="text-center text-muted py-5" data-testid="google-accounts-empty">
              {t('No Google accounts linked yet')}
            </div>
          ) : (
            <Table hover responsive className="mb-0 align-middle">
              <thead>
                <tr>
                  <th>{t('Email')}</th>
                  <th>{t('Status')}</th>
                  <th>{t('Scopes')}</th>
                  <th>{t('Last Synced')}</th>
                  <th>{t('Token')}</th>
                  <th className="text-end">{t('Actions')}</th>
                </tr>
              </thead>
              <tbody data-testid="google-accounts-table">
                {accounts.map((account) => (
                  <tr key={account.id}>
                    <td className="fw-semibold">{account.email}</td>
                    <td>
                      <Badge bg={account.status === 'active' ? 'success' : 'secondary'}>
                        {account.status === 'active' ? t('Active') : t('Disabled')}
                      </Badge>
                    </td>
                    <td>
                      <span className="text-muted small">
                        {account.scopes.length > 0
                          ? t('{{count}} scope(s)', { count: account.scopes.length })
                          : '—'}
                      </span>
                    </td>
                    <td className="small">{formatDateTime(account.last_synced_at)}</td>
                    <td>
                      <Badge bg={account.has_token ? 'success' : 'danger'}>
                        {account.has_token ? t('Yes') : t('No')}
                      </Badge>
                    </td>
                    <td className="text-end">
                      {testResult?.id === account.id && (
                        <Badge
                          bg={testResult.ok ? 'success' : 'danger'}
                          className="me-2"
                          data-testid="google-test-result"
                        >
                          {testResult.ok
                            ? t('Connection OK')
                            : testResult.message || t('Connection failed')}
                        </Badge>
                      )}
                      <div className="btn-group btn-group-sm">
                        <Button
                          variant="outline-secondary"
                          onClick={() => handleTest(account)}
                          disabled={busyAccountId === account.id || !account.has_token}
                          title={t('Test connection')}
                          data-testid="google-test-btn"
                        >
                          <i className="fa-solid fa-plug" />
                        </Button>
                        <Button
                          variant="outline-secondary"
                          onClick={() => handleToggleStatus(account)}
                          disabled={busyAccountId === account.id}
                          title={account.status === 'active' ? t('Disable') : t('Enable')}
                          data-testid="google-toggle-btn"
                        >
                          <i className={`fa-solid ${account.status === 'active' ? 'fa-pause' : 'fa-play'}`} />
                        </Button>
                        <Button
                          variant="outline-danger"
                          onClick={() => setDeleteTarget(account)}
                          disabled={busyAccountId === account.id}
                          title={t('Unlink')}
                          data-testid="google-unlink-btn"
                        >
                          <i className="fa-solid fa-link-slash" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card.Body>
      </Card>

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
    </Container>
  );
};

export default GoogleAccountsPage;

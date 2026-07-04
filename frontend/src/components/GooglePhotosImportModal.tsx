import React, { useEffect, useState } from 'react';
import { Alert, Button, Form, Modal, Spinner } from 'react-bootstrap';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../services/api';
import { LinkedGoogleAccount, PickerSessionCreateResponse } from '../types/api';

interface GooglePhotosImportModalProps {
  show: boolean;
  onHide: () => void;
  // Picker セッション作成成功時に呼ばれる（pickerUri は別タブで開いた後）
  onCreated: (session: PickerSessionCreateResponse) => void;
}

// Google フォトからのインポート開始モーダル。
// 連携済みアカウントを選択して Picker セッションを作成し、
// Google フォトの選択画面を新しいタブで開く。
// アカウント未登録の場合はプロフィールの登録セクションへ誘導する。
const GooglePhotosImportModal: React.FC<GooglePhotosImportModalProps> = ({
  show,
  onHide,
  onCreated,
}) => {
  const { t } = useTranslation();

  const [accounts, setAccounts] = useState<LinkedGoogleAccount[]>([]);
  const [accountsLoading, setAccountsLoading] = useState(false);
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    if (!show) return;
    let cancelled = false;
    (async () => {
      setError(null);
      setAccountsLoading(true);
      try {
        const data = await apiClient.getLinkedGoogleAccounts({ mine: true });
        const usable = (data.items || []).filter((a) => a.status === 'active' && a.has_token);
        if (!cancelled) {
          setAccounts(usable);
          setSelectedAccountId(usable.length > 0 ? usable[0].id : null);
        }
      } catch (e: any) {
        if (!cancelled) {
          setError(e?.response?.data?.error || e?.message || t('Failed to load Google accounts'));
        }
      } finally {
        if (!cancelled) setAccountsLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [show, t]);

  const handleCreate = async () => {
    if (selectedAccountId == null) return;
    setCreating(true);
    setError(null);
    try {
      const res = await apiClient.createPickerSession(selectedAccountId);
      if (res.pickerUri) {
        // Google Photos Picker を新しいタブで開く
        window.open(res.pickerUri, '_blank', 'noopener');
      }
      onCreated(res);
      onHide();
    } catch (e: any) {
      setError(
        e?.response?.data?.message || e?.response?.data?.error || e?.message || t('Failed to create picker session')
      );
    } finally {
      setCreating(false);
    }
  };

  return (
    <Modal show={show} onHide={onHide} centered data-testid="google-import-modal">
      <Modal.Header closeButton>
        <Modal.Title>{t('Import from Google Photos')}</Modal.Title>
      </Modal.Header>
      <Modal.Body>
        {error && <Alert variant="danger">{error}</Alert>}
        {accountsLoading ? (
          <div className="text-center py-4"><Spinner animation="border" /></div>
        ) : accounts.length === 0 ? (
          <div className="text-muted" data-testid="google-import-no-accounts">
            {t('No active Google account is linked.')}{' '}
            <Link to="/profile#google-accounts" onClick={onHide}>
              {t('Link a Google account in your profile')}
            </Link>
          </div>
        ) : (
          <>
            <p className="text-muted small">
              {t('A Google Photos Picker session will be created and opened in a new tab. Photos you select there will be imported.')}
            </p>
            <Form.Group>
              <Form.Label>{t('Google account')}</Form.Label>
              <Form.Select
                value={selectedAccountId ?? ''}
                onChange={(e) => setSelectedAccountId(Number(e.target.value))}
                data-testid="google-import-account-select"
              >
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>{a.email}</option>
                ))}
              </Form.Select>
            </Form.Group>
          </>
        )}
      </Modal.Body>
      <Modal.Footer>
        <Button variant="secondary" onClick={onHide}>{t('Cancel')}</Button>
        <Button
          variant="primary"
          onClick={handleCreate}
          disabled={creating || selectedAccountId == null || accounts.length === 0}
          data-testid="google-import-start"
        >
          {creating ? (
            <><Spinner size="sm" animation="border" className="me-1" />{t('Creating...')}</>
          ) : (
            t('Start Import')
          )}
        </Button>
      </Modal.Footer>
    </Modal>
  );
};

export default GooglePhotosImportModal;

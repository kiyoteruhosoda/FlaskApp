import React, { useCallback, useEffect, useState } from 'react';
import {
  Container,
  Row,
  Col,
  Card,
  Table,
  Badge,
  Button,
  Spinner,
  Alert,
  Pagination as BsPagination,
} from 'react-bootstrap';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../services/api';
import { PickerSessionRow } from '../types/api';
import GooglePhotosImportModal from '../components/GooglePhotosImportModal';
import {
  formatDateTime,
  formatCounts,
} from '../utils/format';
import { describeImportSessionStatus } from '../utils/importSessionStatus';

const SessionsPage: React.FC = () => {
  const { t } = useTranslation();

  const [sessions, setSessions] = useState<PickerSessionRow[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [hasNext, setHasNext] = useState(false);
  const [totalCount, setTotalCount] = useState<number | null>(null);

  // Google Photos インポート（Picker セッション作成）
  const [showImport, setShowImport] = useState(false);
  const [pickerNotice, setPickerNotice] = useState<{ sessionId: string; pickerUri: string | null } | null>(null);

  const loadSessions = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiClient.getPickerSessions({ page, pageSize: 50 });
      setSessions(data.sessions);
      setHasNext(data.pagination?.hasNext ?? false);
      setTotalCount(data.pagination?.totalCount ?? null);
    } catch (e: any) {
      setError(e?.response?.data?.error || e?.message || t('Failed to load sessions'));
    } finally {
      setIsLoading(false);
    }
  }, [page, t]);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  return (
    <Container fluid className="py-4" data-testid="sessions-page">
      <Row className="mb-3">
        <Col>
          <h1 className="h3 mb-1">{t('Import Sessions')}</h1>
          <p className="text-muted mb-0">
            {t('Picker and local import sessions')}
          </p>
        </Col>
        <Col xs="auto" className="d-flex align-items-center gap-2">
          <Button
            variant="outline-primary"
            onClick={loadSessions}
            data-testid="sessions-refresh"
          >
            <i className="fa-solid fa-rotate-right me-1" />
            {t('Refresh')}
          </Button>
          <Button
            variant="primary"
            onClick={() => setShowImport(true)}
            data-testid="google-import-btn"
          >
            <i className="fa-brands fa-google me-1" />
            {t('Import from Google Photos')}
          </Button>
        </Col>
      </Row>

      {error && (
        <Alert variant="danger" dismissible onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {pickerNotice && (
        <Alert
          variant="success"
          dismissible
          onClose={() => setPickerNotice(null)}
          data-testid="picker-created-alert"
        >
          {t('Picker session created. Select photos in the opened Google Photos tab.')}{' '}
          {pickerNotice.pickerUri && (
            <a href={pickerNotice.pickerUri} target="_blank" rel="noopener noreferrer">
              {t('Open Google Photos Picker')}
            </a>
          )}{' '}
          <Link to={`/sessions/${encodeURIComponent(pickerNotice.sessionId)}`}>
            {t('View session progress')}
          </Link>
        </Alert>
      )}

      <Card>
        <Card.Body className="p-0">
          {isLoading ? (
            <div className="text-center py-5">
              <Spinner animation="border" role="status" />
            </div>
          ) : sessions.length === 0 ? (
            <div className="text-center text-muted py-5" data-testid="sessions-empty">
              {t('No sessions found')}
            </div>
          ) : (
            <Table hover responsive className="mb-0 align-middle">
              <thead>
                <tr>
                  <th>{t('Session')}</th>
                  <th>{t('Type')}</th>
                  <th>{t('Account')}</th>
                  <th>{t('Status')}</th>
                  <th>{t('Selected')}</th>
                  <th>{t('Counts')}</th>
                  <th>{t('Created')}</th>
                  <th>{t('Last Progress')}</th>
                  <th className="text-end">{t('Actions')}</th>
                </tr>
              </thead>
              <tbody>
                {sessions.map((s) => (
                  <tr key={s.id} data-testid="session-row">
                    <td className="small text-break">{s.sessionId}</td>
                    <td>
                      <Badge bg={s.isLocalImport ? 'secondary' : 'info'}>
                        {s.isLocalImport ? t('Local Import') : t('Picker')}
                      </Badge>
                    </td>
                    <td className="small">{s.accountEmail || '—'}</td>
                    <td>
                      <Badge
                        bg={describeImportSessionStatus(s.status).variant}
                        data-testid="session-status"
                        title={s.status}
                      >
                        {t(describeImportSessionStatus(s.status).labelKey)}
                      </Badge>
                    </td>
                    <td>{s.selectedCount}</td>
                    <td className="small">{formatCounts(s.counts) || '—'}</td>
                    <td className="small">{formatDateTime(s.createdAt)}</td>
                    <td className="small">{formatDateTime(s.lastProgressAt)}</td>
                    <td className="text-end">
                      <Link
                        to={`/sessions/${encodeURIComponent(s.sessionId)}`}
                        className="btn btn-sm btn-outline-secondary"
                        data-testid="session-detail-link"
                      >
                        {t('Details')}
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card.Body>
      </Card>

      <div className="d-flex justify-content-between align-items-center mt-3">
        <small className="text-muted">
          {totalCount !== null
            ? t('{{count}} sessions total', { count: totalCount })
            : ''}
        </small>
        <BsPagination className="mb-0">
          <BsPagination.Prev
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          />
          <BsPagination.Item active>{page}</BsPagination.Item>
          <BsPagination.Next
            disabled={!hasNext}
            onClick={() => setPage((p) => p + 1)}
          />
        </BsPagination>
      </div>

      {/* Google Photos インポート: アカウント選択モーダル */}
      <GooglePhotosImportModal
        show={showImport}
        onHide={() => setShowImport(false)}
        onCreated={(res) => {
          setPickerNotice({
            sessionId: res.sessionId || String(res.pickerSessionId),
            pickerUri: res.pickerUri,
          });
          loadSessions();
        }}
      />
    </Container>
  );
};

export default SessionsPage;

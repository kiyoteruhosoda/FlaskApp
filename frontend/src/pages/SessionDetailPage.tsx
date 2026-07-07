import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Container,
  Form,
  Row,
  Spinner,
  Tab,
  Table,
  Tabs,
} from 'react-bootstrap';
import { Link, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../services/api';
import { PickerSessionStatus, PickerSelectionItem, SessionLogEntry } from '../types/api';
import { badgeTextColor, formatDateTime, sessionStatusVariant } from '../utils/format';
import {
  describeImportSessionStatus,
  isActiveImportSessionStatus,
} from '../utils/importSessionStatus';

const LOG_LEVEL_VARIANT: Record<string, string> = {
  ERROR: 'danger',
  WARNING: 'warning',
  INFO: 'info',
  DEBUG: 'secondary',
};

const SessionDetailPage: React.FC = () => {
  const { t } = useTranslation();
  const { sessionId } = useParams<{ sessionId: string }>();

  const [session, setSession] = useState<PickerSessionStatus | null>(null);
  const [selections, setSelections] = useState<PickerSelectionItem[]>([]);
  const [logs, setLogs] = useState<SessionLogEntry[]>([]);
  const [logsHasNext, setLogsHasNext] = useState(false);
  const [logsCursor, setLogsCursor] = useState<number | undefined>(undefined);
  const [statusFilter, setStatusFilter] = useState('');
  const [isLoadingSession, setIsLoadingSession] = useState(false);
  const [isLoadingSelections, setIsLoadingSelections] = useState(false);
  const [isLoadingLogs, setIsLoadingLogs] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadSession = useCallback(async () => {
    if (!sessionId) return;
    setIsLoadingSession(true);
    try {
      const data = await apiClient.getPickerSessionStatus(sessionId);
      setSession(data);
    } catch (e: any) {
      setError(e?.response?.data?.error || e?.message || t('Failed to load session'));
    } finally {
      setIsLoadingSession(false);
    }
  }, [sessionId, t]);

  const loadSelections = useCallback(async () => {
    if (!sessionId) return;
    setIsLoadingSelections(true);
    try {
      const params: any = { pageSize: 200 };
      if (statusFilter) params.status = [statusFilter];
      const data = await apiClient.getPickerSessionSelections(sessionId, params);
      setSelections(data.selections ?? []);
    } catch (e: any) {
      setError(e?.response?.data?.error || e?.message || t('Failed to load selections'));
    } finally {
      setIsLoadingSelections(false);
    }
  }, [sessionId, statusFilter, t]);

  const loadLogs = useCallback(async (cursor?: number) => {
    if (!sessionId) return;
    setIsLoadingLogs(true);
    try {
      const data = await apiClient.getPickerSessionLogs(sessionId, { limit: 100, cursor });
      if (cursor) {
        setLogs((prev) => [...prev, ...data.logs]);
      } else {
        setLogs(data.logs);
      }
      setLogsHasNext(data.hasNext);
      setLogsCursor(data.nextCursor ?? undefined);
    } catch (e: any) {
      setError(e?.response?.data?.error || e?.message || t('Failed to load logs'));
    } finally {
      setIsLoadingLogs(false);
    }
  }, [sessionId, t]);

  useEffect(() => {
    loadSession();
    loadSelections();
    loadLogs();
  }, [loadSession, loadSelections, loadLogs]);

  const handleStatusFilterChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setStatusFilter(e.target.value);
  };

  useEffect(() => {
    loadSelections();
  }, [loadSelections]);

  // 進行中（選択待ち・取り込み中）の間は自動で最新状態に更新する
  useEffect(() => {
    if (!session || !isActiveImportSessionStatus(session.status)) return;
    const timer = setTimeout(() => {
      loadSession();
      loadSelections();
    }, 8000);
    return () => clearTimeout(timer);
  }, [session, loadSession, loadSelections]);

  if (isLoadingSession && !session) {
    return (
      <Container fluid className="py-5 text-center">
        <Spinner animation="border" />
      </Container>
    );
  }

  return (
    <Container fluid className="py-4" data-testid="session-detail-page">
      <Row className="mb-3 align-items-center">
        <Col>
          <nav aria-label="breadcrumb">
            <ol className="breadcrumb mb-1">
              <li className="breadcrumb-item">
                <Link to="/sessions">{t('Import Sessions')}</Link>
              </li>
              <li className="breadcrumb-item active">{t('Detail')}</li>
            </ol>
          </nav>
          <h1 className="h4 mb-0 text-break">{sessionId}</h1>
        </Col>
        <Col xs="auto">
          <Button variant="outline-secondary" size="sm" onClick={() => { loadSession(); loadSelections(); loadLogs(); }}>
            <i className="fa-solid fa-rotate-right me-1" />
            {t('Refresh')}
          </Button>
        </Col>
      </Row>

      {error && (
        <Alert variant="danger" dismissible onClose={() => setError(null)}>{error}</Alert>
      )}

      {session && (
        <Card className="mb-4">
          <Card.Body>
            <Row>
              <Col md={3}>
                <div className="text-muted small">{t('Status')}</div>
                <Badge
                  bg={describeImportSessionStatus(session.status).variant}
                  data-testid="session-status-badge"
                  title={session.status}
                >
                  {t(describeImportSessionStatus(session.status).labelKey)}
                </Badge>
              </Col>
              <Col md={3}>
                <div className="text-muted small">{t('Type')}</div>
                <Badge bg={session.isLocalImport ? 'secondary' : 'info'}>
                  {session.isLocalImport ? t('Local Import') : t('Picker')}
                </Badge>
              </Col>
              <Col md={3}>
                <div className="text-muted small">{t('Account')}</div>
                <div>{session.accountEmail || '—'}</div>
              </Col>
              <Col md={3}>
                <div className="text-muted small">{t('Selected')}</div>
                <div>{session.selectedCount ?? '—'}</div>
              </Col>
            </Row>
            <Row className="mt-3">
              <Col md={3}>
                <div className="text-muted small">{t('Created')}</div>
                <div>{formatDateTime(session.createdAt)}</div>
              </Col>
              <Col md={3}>
                <div className="text-muted small">{t('Last Progress')}</div>
                <div>{formatDateTime(session.lastProgressAt)}</div>
              </Col>
              {session.counts && Object.keys(session.counts).length > 0 && (
                <Col md={6}>
                  <div className="text-muted small">{t('Counts')}</div>
                  <div className="d-flex flex-wrap gap-1 mt-1">
                    {Object.entries(session.counts).map(([status, count]) => (
                      <Badge key={status} bg={sessionStatusVariant(status)} text={badgeTextColor(sessionStatusVariant(status))}>
                        {status}: {count}
                      </Badge>
                    ))}
                  </div>
                </Col>
              )}
            </Row>
          </Card.Body>
        </Card>
      )}

      <Tabs defaultActiveKey="selections" className="mb-3" data-testid="session-tabs">
        <Tab eventKey="selections" title={t('Selections ({{count}})', { count: selections.length })}>
          <Card>
            <Card.Header>
              <Row className="align-items-center">
                <Col xs="auto">
                  <Form.Select size="sm" value={statusFilter} onChange={handleStatusFilterChange} style={{ width: 160 }} data-testid="selections-status-filter">
                    <option value="">{t('All statuses')}</option>
                    {['imported', 'failed', 'dup', 'skipped', 'pending', 'enqueued', 'running'].map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </Form.Select>
                </Col>
              </Row>
            </Card.Header>
            <Card.Body className="p-0">
              {isLoadingSelections ? (
                <div className="text-center py-4"><Spinner animation="border" /></div>
              ) : selections.length === 0 ? (
                <div className="text-center text-muted py-4" data-testid="selections-empty">{t('No selections')}</div>
              ) : (
                <Table hover responsive className="mb-0 align-middle small">
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>{t('Filename')}</th>
                      <th>{t('Status')}</th>
                      <th>{t('Attempts')}</th>
                      <th>{t('Error')}</th>
                      <th>{t('Finished')}</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {selections.map((sel) => (
                      <tr key={sel.id} data-testid="selection-row">
                        <td>{sel.id}</td>
                        <td className="text-break">{sel.filename || sel.googleMediaId || '—'}</td>
                        <td>
                          <Badge bg={sessionStatusVariant(sel.status)} text={badgeTextColor(sessionStatusVariant(sel.status))}>{sel.status}</Badge>
                        </td>
                        <td>{sel.attempts}</td>
                        <td className="text-danger text-break">{sel.error ? sel.error.slice(0, 80) : '—'}</td>
                        <td>{formatDateTime(sel.finishedAt)}</td>
                        <td>
                          {sel.status === 'failed' && sessionId && (
                            <Link
                              to={`/sessions/${encodeURIComponent(sessionId)}/selection/${sel.id}/error`}
                              className="btn btn-sm btn-outline-danger"
                              data-testid="selection-error-link"
                            >
                              {t('Error Detail')}
                            </Link>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              )}
            </Card.Body>
          </Card>
        </Tab>

        <Tab eventKey="logs" title={t('Logs')}>
          <Card>
            <Card.Body className="p-0">
              {isLoadingLogs && logs.length === 0 ? (
                <div className="text-center py-4"><Spinner animation="border" /></div>
              ) : logs.length === 0 ? (
                <div className="text-center text-muted py-4" data-testid="logs-empty">{t('No logs')}</div>
              ) : (
                <>
                  <div className="overflow-auto" style={{ maxHeight: 500 }} data-testid="logs-list">
                    <Table hover responsive className="mb-0 align-middle small font-monospace">
                      <thead>
                        <tr>
                          <th style={{ width: 160 }}>{t('Timestamp')}</th>
                          <th style={{ width: 80 }}>{t('Level')}</th>
                          <th>{t('Message')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {logs.map((log) => (
                          <tr key={log.id}>
                            <td className="text-nowrap">{log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : '—'}</td>
                            <td>
                              <Badge bg={LOG_LEVEL_VARIANT[log.level] ?? 'secondary'}>{log.level}</Badge>
                            </td>
                            <td className="text-break">{log.message}</td>
                          </tr>
                        ))}
                      </tbody>
                    </Table>
                  </div>
                  {logsHasNext && (
                    <div className="p-3 text-center border-top">
                      <Button
                        variant="outline-secondary"
                        size="sm"
                        onClick={() => loadLogs(logsCursor)}
                        disabled={isLoadingLogs}
                        data-testid="logs-load-more"
                      >
                        {isLoadingLogs ? <Spinner size="sm" animation="border" /> : t('Load more')}
                      </Button>
                    </div>
                  )}
                </>
              )}
            </Card.Body>
          </Card>
        </Tab>
      </Tabs>
    </Container>
  );
};

export default SessionDetailPage;

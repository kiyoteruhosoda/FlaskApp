import React, { useCallback, useEffect, useState } from 'react';
import {
  Container,
  Row,
  Col,
  Card,
  Table,
  Badge,
  Button,
  Form,
  Spinner,
  Alert,
  Modal,
  Pagination as BsPagination,
} from 'react-bootstrap';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { apiClient } from '../services/api';
import {
  AdminLogEntry,
  AdminLogDetail,
  AdminLogSource,
  AdminLogsQuery,
  Pagination as PaginationMeta,
} from '../types/api';
import { badgeTextColor, formatDateTime } from '../utils/format';
import { getApiErrorCode } from '../services/apiErrors';

const PAGE_SIZE = 50;

const levelVariant = (level: string): string => {
  switch ((level || '').toUpperCase()) {
    case 'CRITICAL':
    case 'FATAL':
    case 'ERROR':
      return 'danger';
    case 'WARNING':
    case 'WARN':
      return 'warning';
    case 'DEBUG':
      return 'secondary';
    default:
      return 'info';
  }
};

/** datetime-local 入力（ローカル時刻）を ISO 8601 UTC 文字列に変換する。 */
const toIsoUtc = (localValue: string): string | undefined => {
  if (!localValue) return undefined;
  const parsed = new Date(localValue);
  if (Number.isNaN(parsed.getTime())) return undefined;
  return parsed.toISOString();
};

/** ログ詳細を、そのままクリップボードへ貼り付けられるプレーンテキストへ整形する。 */
const buildLogDetailText = (
  detail: AdminLogDetail,
  t: TFunction,
): string => {
  const lines: string[] = [];
  lines.push(`${t('Log Detail')} #${detail.id}`);
  lines.push(`${t('Time (UTC)')}: ${formatDateTime(detail.createdAt)}`);
  lines.push(`${t('Level')}: ${detail.level}`);
  lines.push(`${t('Event')}: ${detail.event || '—'}`);
  if (detail.source === 'app') {
    lines.push(`${t('Path')}: ${detail.path || '—'}`);
    lines.push(`${t('Request ID')}: ${detail.requestId || '—'}`);
  } else {
    lines.push(`${t('Task')}: ${detail.taskName || '—'}`);
    lines.push(`${t('Task ID')}: ${detail.taskUuid || detail.fileTaskId || '—'}`);
    const worker = `${detail.workerHostname || '—'}${detail.queueName ? ` (${detail.queueName})` : ''}`;
    lines.push(`${t('Worker')}: ${worker}`);
  }
  lines.push('');
  lines.push(`${t('Message')}:`);
  lines.push(detail.message || '');
  if (detail.trace) {
    lines.push('');
    lines.push(`${t('Traceback')}:`);
    lines.push(detail.trace);
  }
  return lines.join('\n');
};

/** クリップボードへ書き込む。Clipboard API 不可の環境ではフォールバックする。 */
const copyToClipboard = async (text: string): Promise<boolean> => {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // セキュアコンテキスト外などで失敗した場合は下のフォールバックへ。
  }
  try {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(textarea);
    return ok;
  } catch {
    return false;
  }
};

const SystemLogsPage: React.FC = () => {
  const { t } = useTranslation();

  const [logs, setLogs] = useState<AdminLogEntry[]>([]);
  const [pagination, setPagination] = useState<PaginationMeta | null>(null);
  const [availableLevels, setAvailableLevels] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [page, setPage] = useState(1);
  const [source, setSource] = useState<AdminLogSource>('app');
  const [level, setLevel] = useState('');
  const [event, setEvent] = useState('');
  const [message, setMessage] = useState('');
  const [traceId, setTraceId] = useState('');
  const [since, setSince] = useState('');
  const [until, setUntil] = useState('');
  // テキスト入力は「Apply」で確定させる（1文字ごとのAPI呼び出しを避ける）
  const [appliedText, setAppliedText] = useState({ event: '', message: '', traceId: '' });

  const [detail, setDetail] = useState<AdminLogDetail | null>(null);
  const [showDetail, setShowDetail] = useState(false);
  const [copied, setCopied] = useState(false);

  const loadLogs = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const query: AdminLogsQuery = { source, page, pageSize: PAGE_SIZE };
      if (level) query.level = level;
      if (appliedText.event) query.event = appliedText.event;
      if (appliedText.message) query.q = appliedText.message;
      if (appliedText.traceId) query.traceId = appliedText.traceId;
      const sinceIso = toIsoUtc(since);
      if (sinceIso) query.since = sinceIso;
      const untilIso = toIsoUtc(until);
      if (untilIso) query.until = untilIso;

      const data = await apiClient.getAdminLogs(query);
      setLogs(data.logs);
      setPagination(data.pagination);
      setAvailableLevels(data.availableLevels);
    } catch (e: any) {
      setError(getApiErrorCode(e) || e?.message || t('Failed to load logs'));
    } finally {
      setIsLoading(false);
    }
  }, [source, page, level, appliedText, since, until, t]);

  useEffect(() => {
    loadLogs();
  }, [loadLogs]);

  const applyTextFilters = () => {
    setAppliedText({ event, message, traceId });
    setPage(1);
  };

  const resetFilters = () => {
    setLevel('');
    setEvent('');
    setMessage('');
    setTraceId('');
    setSince('');
    setUntil('');
    setAppliedText({ event: '', message: '', traceId: '' });
    setPage(1);
  };

  const openDetail = async (log: AdminLogEntry) => {
    setShowDetail(true);
    setDetail(null);
    setCopied(false);
    try {
      const data = await apiClient.getAdminLogDetail(log.source, log.id);
      setDetail(data.log);
    } catch (e: any) {
      setError(getApiErrorCode(e) || e?.message || t('Failed to load log detail'));
      setShowDetail(false);
    }
  };

  const handleCopyDetail = async () => {
    if (!detail) return;
    const ok = await copyToClipboard(buildLogDetailText(detail, t));
    if (ok) {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } else {
      setError(t('Failed to copy log detail to clipboard'));
    }
  };

  return (
    <Container fluid className="py-4" data-testid="system-logs-page">
      <Row className="mb-3">
        <Col>
          <h1 className="h3 mb-1">{t('System Logs')}</h1>
          <p className="text-muted mb-0">
            {t('Logs recorded in the database (API requests and background jobs)')}
          </p>
        </Col>
        <Col xs="auto" className="d-flex align-items-center">
          <Button variant="outline-primary" onClick={loadLogs} data-testid="logs-refresh">
            <i className="fa-solid fa-rotate-right me-1" />
            {t('Refresh')}
          </Button>
        </Col>
      </Row>

      {error && (
        <Alert variant="danger" dismissible onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      <Card className="mb-3">
        <Card.Body>
          <Row className="g-2 align-items-end">
            <Col md={2}>
              <Form.Label>{t('Source')}</Form.Label>
              <Form.Select
                value={source}
                data-testid="filter-source"
                onChange={(e) => {
                  setSource(e.target.value as AdminLogSource);
                  setLevel('');
                  setPage(1);
                }}
              >
                <option value="app">{t('App (API requests)')}</option>
                <option value="worker">{t('Worker (background jobs)')}</option>
              </Form.Select>
            </Col>
            <Col md={2}>
              <Form.Label>{t('Level')}</Form.Label>
              <Form.Select
                value={level}
                data-testid="filter-level"
                onChange={(e) => {
                  setLevel(e.target.value);
                  setPage(1);
                }}
              >
                <option value="">{t('All')}</option>
                {availableLevels.map((lv) => (
                  <option key={lv} value={lv}>
                    {lv}
                  </option>
                ))}
              </Form.Select>
            </Col>
            <Col md={4}>
              <Form.Label>{t('From')}</Form.Label>
              <Form.Control
                type="datetime-local"
                value={since}
                data-testid="filter-since"
                onChange={(e) => {
                  setSince(e.target.value);
                  setPage(1);
                }}
              />
            </Col>
            <Col md={4}>
              <Form.Label>{t('To')}</Form.Label>
              <Form.Control
                type="datetime-local"
                value={until}
                data-testid="filter-until"
                onChange={(e) => {
                  setUntil(e.target.value);
                  setPage(1);
                }}
              />
            </Col>
            <Col md={3}>
              <Form.Label>{t('Event')}</Form.Label>
              <Form.Control
                type="text"
                value={event}
                placeholder={t('e.g. request.failed')}
                data-testid="filter-event"
                onChange={(e) => setEvent(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && applyTextFilters()}
              />
            </Col>
            <Col md={3}>
              <Form.Label>{t('Message contains')}</Form.Label>
              <Form.Control
                type="text"
                value={message}
                data-testid="filter-message"
                onChange={(e) => setMessage(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && applyTextFilters()}
              />
            </Col>
            <Col md={3}>
              <Form.Label>
                {source === 'app' ? t('Request ID') : t('Task ID')}
              </Form.Label>
              <Form.Control
                type="text"
                value={traceId}
                data-testid="filter-trace-id"
                onChange={(e) => setTraceId(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && applyTextFilters()}
              />
            </Col>
            <Col md="auto">
              <Button variant="primary" className="me-2" onClick={applyTextFilters} data-testid="filter-apply">
                {t('Apply')}
              </Button>
              <Button variant="outline-secondary" onClick={resetFilters}>
                {t('Reset')}
              </Button>
            </Col>
          </Row>
        </Card.Body>
      </Card>

      <Card>
        <Card.Body className="p-0">
          {isLoading ? (
            <div className="text-center py-5">
              <Spinner animation="border" role="status" />
            </div>
          ) : logs.length === 0 ? (
            <div className="text-center text-muted py-5" data-testid="logs-empty">
              {t('No logs found')}
            </div>
          ) : (
            <Table hover responsive className="mb-0 align-middle">
              <thead>
                <tr>
                  <th style={{ whiteSpace: 'nowrap' }}>{t('Time (UTC)')}</th>
                  <th>{t('Level')}</th>
                  <th>{t('Event')}</th>
                  <th>{t('Message')}</th>
                  <th>{source === 'app' ? t('Path') : t('Task')}</th>
                  <th>{source === 'app' ? t('Request ID') : t('Task ID')}</th>
                  <th className="text-end">{t('Actions')}</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => (
                  <tr key={`${log.source}-${log.id}`} data-testid="log-row">
                    <td className="small" style={{ whiteSpace: 'nowrap' }}>
                      {formatDateTime(log.createdAt)}
                    </td>
                    <td>
                      <Badge
                        bg={levelVariant(log.level)}
                        text={badgeTextColor(levelVariant(log.level))}
                        data-testid="log-level"
                      >
                        {log.level}
                      </Badge>
                    </td>
                    <td className="small">{log.event}</td>
                    <td className="small" style={{ maxWidth: '28rem', wordBreak: 'break-word' }}>
                      {log.message}
                      {log.messageTruncated && <span className="text-muted">…</span>}
                    </td>
                    <td className="small">
                      {log.source === 'app' ? log.path || '—' : log.taskName || '—'}
                    </td>
                    <td className="small font-monospace">
                      {log.source === 'app'
                        ? log.requestId || '—'
                        : log.taskUuid || log.fileTaskId || '—'}
                    </td>
                    <td className="text-end">
                      <Button
                        size="sm"
                        variant="outline-secondary"
                        onClick={() => openDetail(log)}
                        data-testid="log-detail-btn"
                      >
                        {t('Details')}
                        {log.hasTrace && (
                          <i className="fa-solid fa-triangle-exclamation text-danger ms-1" />
                        )}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card.Body>
      </Card>

      {pagination && pagination.totalPages > 1 && (
        <div className="d-flex justify-content-between align-items-center mt-3">
          <small className="text-muted">
            {t('{{count}} logs total', { count: pagination.totalCount })}
          </small>
          <BsPagination className="mb-0">
            <BsPagination.Prev
              disabled={!pagination.hasPrev}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            />
            <BsPagination.Item active>
              {pagination.currentPage} / {pagination.totalPages}
            </BsPagination.Item>
            <BsPagination.Next
              disabled={!pagination.hasNext}
              onClick={() => setPage((p) => p + 1)}
            />
          </BsPagination>
        </div>
      )}

      <Modal show={showDetail} onHide={() => setShowDetail(false)} size="lg" scrollable>
        <Modal.Header closeButton>
          <Modal.Title>
            {t('Log Detail')} {detail ? `#${detail.id}` : ''}
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {!detail ? (
            <div className="text-center py-4">
              <Spinner animation="border" />
            </div>
          ) : (
            <>
              <dl className="row mb-3">
                <dt className="col-sm-3">{t('Time (UTC)')}</dt>
                <dd className="col-sm-9">{formatDateTime(detail.createdAt)}</dd>
                <dt className="col-sm-3">{t('Level')}</dt>
                <dd className="col-sm-9">
                  <Badge bg={levelVariant(detail.level)} text={badgeTextColor(levelVariant(detail.level))}>
                    {detail.level}
                  </Badge>
                </dd>
                <dt className="col-sm-3">{t('Event')}</dt>
                <dd className="col-sm-9">{detail.event}</dd>
                {detail.source === 'app' ? (
                  <>
                    <dt className="col-sm-3">{t('Path')}</dt>
                    <dd className="col-sm-9">{detail.path || '—'}</dd>
                    <dt className="col-sm-3">{t('Request ID')}</dt>
                    <dd className="col-sm-9 font-monospace">{detail.requestId || '—'}</dd>
                  </>
                ) : (
                  <>
                    <dt className="col-sm-3">{t('Task')}</dt>
                    <dd className="col-sm-9">{detail.taskName || '—'}</dd>
                    <dt className="col-sm-3">{t('Task ID')}</dt>
                    <dd className="col-sm-9 font-monospace">
                      {detail.taskUuid || detail.fileTaskId || '—'}
                    </dd>
                    <dt className="col-sm-3">{t('Worker')}</dt>
                    <dd className="col-sm-9">
                      {detail.workerHostname || '—'}
                      {detail.queueName ? ` (${detail.queueName})` : ''}
                    </dd>
                  </>
                )}
              </dl>
              <h6>{t('Message')}</h6>
              <pre className="bg-light p-2 rounded small" style={{ whiteSpace: 'pre-wrap' }} data-testid="log-detail-message">
                {detail.message}
              </pre>
              {detail.trace && (
                <>
                  <h6 className="text-danger">{t('Traceback')}</h6>
                  <pre className="bg-light p-2 rounded small" style={{ whiteSpace: 'pre-wrap' }} data-testid="log-detail-trace">
                    {detail.trace}
                  </pre>
                </>
              )}
            </>
          )}
        </Modal.Body>
        <Modal.Footer>
          <Button
            variant={copied ? 'success' : 'outline-primary'}
            onClick={handleCopyDetail}
            disabled={!detail}
            data-testid="log-detail-copy"
          >
            {copied ? (
              <><i className="fa-solid fa-check me-1" />{t('Copied')}</>
            ) : (
              <><i className="fa-regular fa-copy me-1" />{t('Copy')}</>
            )}
          </Button>
          <Button variant="secondary" onClick={() => setShowDetail(false)}>
            {t('Close')}
          </Button>
        </Modal.Footer>
      </Modal>
    </Container>
  );
};

export default SystemLogsPage;

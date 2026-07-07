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
import { apiClient } from '../services/api';
import {
  SyncJob,
  SyncJobDetail,
  SyncJobsQuery,
  Pagination as PaginationMeta,
  JobStatus,
  JobTargetCategory,
} from '../types/api';
import {
  badgeTextColor,
  formatDateTime,
  formatDuration,
  formatCounts,
  jobStatusVariant,
} from '../utils/format';

const STATUS_OPTIONS: JobStatus[] = [
  'queued',
  'running',
  'success',
  'partial',
  'failed',
  'canceled',
];

const TARGET_OPTIONS: JobTargetCategory[] = [
  'local_import',
  'picker_import',
  'transcode',
  'thumbnail',
  'google_photos',
  'other',
];

const JobsPage: React.FC = () => {
  const { t } = useTranslation();

  const [jobs, setJobs] = useState<SyncJob[]>([]);
  const [pagination, setPagination] = useState<PaginationMeta | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<JobStatus | ''>('');
  const [target, setTarget] = useState<JobTargetCategory | ''>('');

  const [detail, setDetail] = useState<SyncJobDetail | null>(null);
  const [showDetail, setShowDetail] = useState(false);

  const loadJobs = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const query: SyncJobsQuery = { page, pageSize: 50 };
      if (status) query.status = status;
      if (target) query.target = target;
      const data = await apiClient.getSyncJobs(query);
      setJobs(data.jobs);
      setPagination(data.pagination);
    } catch (e: any) {
      setError(e?.response?.data?.error || e?.message || t('Failed to load jobs'));
    } finally {
      setIsLoading(false);
    }
  }, [page, status, target, t]);

  useEffect(() => {
    loadJobs();
  }, [loadJobs]);

  const openDetail = async (job: SyncJob) => {
    setShowDetail(true);
    setDetail(null);
    try {
      const data = await apiClient.getSyncJob(job.id);
      setDetail(data.job);
    } catch (e: any) {
      setError(e?.message || t('Failed to load job detail'));
      setShowDetail(false);
    }
  };

  const [retryingId, setRetryingId] = useState<number | null>(null);

  const handleRetry = async (job: SyncJob) => {
    setRetryingId(job.id);
    setInfo(null);
    setError(null);
    try {
      const res = await apiClient.retrySyncJob(job.id);
      setInfo(
        t('Job #{{id}} re-queued (new job #{{newId}}).', {
          id: job.id,
          newId: res.newJobId,
        })
      );
      await loadJobs();
    } catch (e: any) {
      setError(
        e?.response?.data?.error || e?.message || t('Failed to retry job')
      );
    } finally {
      setRetryingId(null);
    }
  };

  const downloadJson = () => {
    if (!detail) return;
    const blob = new Blob([JSON.stringify(detail, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `job_${detail.id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const resetFilters = () => {
    setStatus('');
    setTarget('');
    setPage(1);
  };

  return (
    <Container fluid className="py-4" data-testid="jobs-page">
      <Row className="mb-3">
        <Col>
          <h1 className="h3 mb-1">{t('Sync Job History')}</h1>
          <p className="text-muted mb-0">
            {t('History of sync and transcode jobs')}
          </p>
        </Col>
        <Col xs="auto" className="d-flex align-items-center">
          <Button variant="outline-primary" onClick={loadJobs} data-testid="jobs-refresh">
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
      {info && (
        <Alert variant="info" dismissible onClose={() => setInfo(null)}>
          {info}
        </Alert>
      )}

      <Card className="mb-3">
        <Card.Body>
          <Row className="g-2 align-items-end">
            <Col md={3}>
              <Form.Label>{t('Status')}</Form.Label>
              <Form.Select
                value={status}
                data-testid="filter-status"
                onChange={(e) => {
                  setStatus(e.target.value as JobStatus | '');
                  setPage(1);
                }}
              >
                <option value="">{t('All')}</option>
                {STATUS_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </Form.Select>
            </Col>
            <Col md={3}>
              <Form.Label>{t('Target')}</Form.Label>
              <Form.Select
                value={target}
                data-testid="filter-target"
                onChange={(e) => {
                  setTarget(e.target.value as JobTargetCategory | '');
                  setPage(1);
                }}
              >
                <option value="">{t('All')}</option>
                {TARGET_OPTIONS.map((tg) => (
                  <option key={tg} value={tg}>
                    {tg}
                  </option>
                ))}
              </Form.Select>
            </Col>
            <Col md="auto">
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
          ) : jobs.length === 0 ? (
            <div className="text-center text-muted py-5" data-testid="jobs-empty">
              {t('No jobs found')}
            </div>
          ) : (
            <Table hover responsive className="mb-0 align-middle">
              <thead>
                <tr>
                  <th>{t('Started')}</th>
                  <th>{t('Finished')}</th>
                  <th>{t('Target')}</th>
                  <th>{t('Status')}</th>
                  <th>{t('Trigger')}</th>
                  <th>{t('Counts')}</th>
                  <th>{t('Duration')}</th>
                  <th className="text-end">{t('Actions')}</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr key={job.id} data-testid="job-row">
                    <td>{formatDateTime(job.startedAt)}</td>
                    <td>{formatDateTime(job.finishedAt)}</td>
                    <td>
                      <Badge bg="info" className="me-1">
                        {job.targetCategory}
                      </Badge>
                      <span className="text-muted small">{job.target}</span>
                    </td>
                    <td>
                      <Badge bg={jobStatusVariant(job.status)} text={badgeTextColor(jobStatusVariant(job.status))} data-testid="job-status">
                        {job.status}
                      </Badge>
                    </td>
                    <td className="small">{job.trigger || '—'}</td>
                    <td className="small">{formatCounts(job.statsSummary) || '—'}</td>
                    <td className="small">{formatDuration(job.durationMs)}</td>
                    <td className="text-end">
                      <Button
                        size="sm"
                        variant="outline-secondary"
                        className="me-1"
                        onClick={() => openDetail(job)}
                        data-testid="job-detail-btn"
                      >
                        {t('Details')}
                      </Button>
                      {job.retryable && (
                        <Button
                          size="sm"
                          variant="outline-warning"
                          disabled={retryingId === job.id}
                          onClick={() => handleRetry(job)}
                          data-testid="job-retry-btn"
                        >
                          {retryingId === job.id ? t('Retrying...') : t('Retry')}
                        </Button>
                      )}
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
            {t('{{count}} jobs total', { count: pagination.totalCount })}
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
            {t('Job Detail')} {detail ? `#${detail.id}` : ''}
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
                <dt className="col-sm-3">{t('Target')}</dt>
                <dd className="col-sm-9">
                  {detail.target}{' '}
                  <Badge bg="info">{detail.targetCategory}</Badge>
                </dd>
                <dt className="col-sm-3">{t('Status')}</dt>
                <dd className="col-sm-9">
                  <Badge bg={jobStatusVariant(detail.status)} text={badgeTextColor(jobStatusVariant(detail.status))}>{detail.status}</Badge>
                </dd>
                <dt className="col-sm-3">{t('Started')}</dt>
                <dd className="col-sm-9">{formatDateTime(detail.startedAt)}</dd>
                <dt className="col-sm-3">{t('Finished')}</dt>
                <dd className="col-sm-9">{formatDateTime(detail.finishedAt)}</dd>
                {detail.errorMessage && (
                  <>
                    <dt className="col-sm-3 text-danger">{t('Error')}</dt>
                    <dd className="col-sm-9 text-danger">{detail.errorMessage}</dd>
                  </>
                )}
              </dl>
              <h6>{t('Stats')}</h6>
              <pre className="bg-light p-2 rounded small" data-testid="job-detail-stats">
                {JSON.stringify(detail.stats, null, 2)}
              </pre>
            </>
          )}
        </Modal.Body>
        <Modal.Footer>
          <Button variant="outline-secondary" onClick={downloadJson} disabled={!detail}>
            {t('Download JSON')}
          </Button>
          <Button variant="secondary" onClick={() => setShowDetail(false)}>
            {t('Close')}
          </Button>
        </Modal.Footer>
      </Modal>
    </Container>
  );
};

export default JobsPage;

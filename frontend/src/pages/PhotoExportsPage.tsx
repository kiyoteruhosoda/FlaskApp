import React, { useState } from 'react';
import {
  Alert, Button, Card, Col, Container, Form, Row, Spinner,
} from 'react-bootstrap';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../services/api';

interface ExportPreview {
  matchedCount: number;
  exportCount: number;
  totalBytes: number;
  limit: number;
}

const formatBytes = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB'];
  let value = bytes / 1024;
  let idx = 0;
  while (value >= 1024 && idx < units.length - 1) { value /= 1024; idx++; }
  return `${value.toFixed(1)} ${units[idx]}`;
};

const PhotoExportsPage: React.FC = () => {
  const { t } = useTranslation();

  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [limit, setLimit] = useState(500);

  const [preview, setPreview] = useState<ExportPreview | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [downloadDone, setDownloadDone] = useState(false);

  const handlePreview = async (e: React.FormEvent) => {
    e.preventDefault();
    setPreviewing(true);
    setPreviewError(null);
    setPreview(null);
    setDownloadDone(false);
    try {
      const res = await apiClient.previewPhotoExports({
        dateFrom: dateFrom || undefined,
        dateTo: dateTo || undefined,
        limit,
      });
      setPreview(res);
    } catch (err: any) {
      const code = err?.response?.data?.error;
      if (code === 'invalid_date_from' || code === 'invalid_date_to') {
        setPreviewError(t('Invalid date format'));
      } else if (code === 'invalid_limit') {
        setPreviewError(t('Limit must be between 1 and 5000'));
      } else {
        setPreviewError(t('Failed to preview export'));
      }
    } finally {
      setPreviewing(false);
    }
  };

  const handleDownload = async () => {
    setDownloading(true);
    setDownloadError(null);
    setDownloadDone(false);
    try {
      await apiClient.downloadPhotoExports({
        dateFrom: dateFrom || undefined,
        dateTo: dateTo || undefined,
        limit,
      });
      setDownloadDone(true);
    } catch (err: any) {
      setDownloadError(t('Failed to download export'));
    } finally {
      setDownloading(false);
    }
  };

  return (
    <Container fluid className="py-4" data-testid="photo-exports-page">
      <Row className="mb-3">
        <Col>
          <h1 className="h3 mb-1">{t('Photo Exports')}</h1>
          <p className="text-muted mb-0">{t('Export original photos and videos as a ZIP archive')}</p>
        </Col>
      </Row>

      <Card className="mb-4">
        <Card.Header>{t('Export Filter')}</Card.Header>
        <Card.Body>
          <Form onSubmit={handlePreview}>
            <Row className="g-3 align-items-end">
              <Col md={3}>
                <Form.Group>
                  <Form.Label>{t('From (import date)')}</Form.Label>
                  <Form.Control
                    type="date"
                    value={dateFrom}
                    onChange={(e) => setDateFrom(e.target.value)}
                    data-testid="export-date-from"
                  />
                </Form.Group>
              </Col>
              <Col md={3}>
                <Form.Group>
                  <Form.Label>{t('To (import date)')}</Form.Label>
                  <Form.Control
                    type="date"
                    value={dateTo}
                    onChange={(e) => setDateTo(e.target.value)}
                    data-testid="export-date-to"
                  />
                </Form.Group>
              </Col>
              <Col md={2}>
                <Form.Group>
                  <Form.Label>{t('Max files')}</Form.Label>
                  <Form.Control
                    type="number"
                    min={1}
                    max={5000}
                    value={limit}
                    onChange={(e) => setLimit(Number(e.target.value))}
                    data-testid="export-limit"
                  />
                </Form.Group>
              </Col>
              <Col md="auto">
                <Button type="submit" variant="outline-primary" disabled={previewing} data-testid="export-preview">
                  {previewing
                    ? <><Spinner size="sm" animation="border" className="me-1" />{t('Checking...')}</>
                    : <><i className="fa-solid fa-magnifying-glass me-1" />{t('Preview')}</>}
                </Button>
              </Col>
            </Row>
          </Form>

          {previewError && (
            <Alert variant="danger" className="mt-3" dismissible onClose={() => setPreviewError(null)}>
              {previewError}
            </Alert>
          )}

          {preview && (
            <Alert variant="info" className="mt-3 mb-0">
              <Row className="align-items-center g-2">
                <Col>
                  <strong>{t('{{count}} files matched', { count: preview.matchedCount })}</strong>
                  {preview.matchedCount > preview.exportCount && (
                    <span className="text-muted ms-2">
                      {t('(limited to {{n}})', { n: preview.exportCount })}
                    </span>
                  )}
                  <span className="text-muted ms-3">{formatBytes(preview.totalBytes)}</span>
                </Col>
                <Col xs="auto">
                  {preview.exportCount === 0 ? (
                    <span className="text-muted">{t('No files to export')}</span>
                  ) : (
                    <Button
                      variant="primary"
                      onClick={handleDownload}
                      disabled={downloading}
                      data-testid="export-download"
                    >
                      {downloading
                        ? <><Spinner size="sm" animation="border" className="me-1" />{t('Preparing...')}</>
                        : <><i className="fa-solid fa-download me-1" />{t('Download ZIP')}</>}
                    </Button>
                  )}
                </Col>
              </Row>
            </Alert>
          )}

          {downloadError && (
            <Alert variant="danger" className="mt-3" dismissible onClose={() => setDownloadError(null)}>
              {downloadError}
            </Alert>
          )}

          {downloadDone && (
            <Alert variant="success" className="mt-3" dismissible onClose={() => setDownloadDone(false)}>
              <i className="fa-solid fa-check me-2" />
              {t('Download started')}
            </Alert>
          )}
        </Card.Body>
      </Card>

      <Alert variant="warning">
        <i className="fa-solid fa-triangle-exclamation me-2" />
        {t('Large exports may take time to prepare. The ZIP contains original files only (no thumbnails or playback files).')}
      </Alert>
    </Container>
  );
};

export default PhotoExportsPage;

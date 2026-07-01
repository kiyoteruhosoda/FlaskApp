import React, { useEffect, useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Container,
  Row,
  Spinner,
  Table,
} from 'react-bootstrap';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../services/api';
import { LocalImportStatusResponse } from '../types/api';

const PhotoSettingsPage: React.FC = () => {
  const { t } = useTranslation();

  const [status, setStatus] = useState<LocalImportStatusResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [importTriggering, setImportTriggering] = useState(false);
  const [importMessage, setImportMessage] = useState<string | null>(null);

  const loadStatus = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiClient.getLocalImportStatus();
      setStatus(data);
    } catch (e: any) {
      setError(e?.response?.data?.error || e?.message || t('Failed to load settings'));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadStatus();
  }, []);

  const handleTriggerImport = async () => {
    setImportTriggering(true);
    setImportMessage(null);
    try {
      await apiClient.triggerLocalImport();
      setImportMessage(t('Import triggered successfully'));
      loadStatus();
    } catch (e: any) {
      setImportMessage(e?.response?.data?.error || e?.message || t('Failed to trigger import'));
    } finally {
      setImportTriggering(false);
    }
  };

  return (
    <Container fluid className="py-4" data-testid="photo-settings-page">
      <Row className="mb-4 align-items-center">
        <Col>
          <h1 className="h3 mb-1">{t('Photo Settings')}</h1>
          <p className="text-muted mb-0">{t('NAS paths, thumbnail conversion, and sync status')}</p>
        </Col>
        <Col xs="auto">
          <Button variant="outline-secondary" size="sm" onClick={loadStatus} disabled={isLoading}>
            <i className="fa-solid fa-rotate-right me-1" />
            {t('Refresh')}
          </Button>
        </Col>
      </Row>

      {error && <Alert variant="danger" dismissible onClose={() => setError(null)}>{error}</Alert>}
      {importMessage && (
        <Alert
          variant={importMessage.includes('success') || importMessage.includes('triggered') ? 'success' : 'danger'}
          dismissible
          onClose={() => setImportMessage(null)}
          data-testid="import-message"
        >
          {importMessage}
        </Alert>
      )}

      {isLoading && !status ? (
        <div className="text-center py-5"><Spinner animation="border" /></div>
      ) : status ? (
        <>
          {/* Directory Status */}
          <Card className="mb-4">
            <Card.Header className="fw-semibold">{t('Directory Status')}</Card.Header>
            <Card.Body className="p-0">
              <Table hover responsive className="mb-0 align-middle small">
                <thead>
                  <tr>
                    <th>{t('Label')}</th>
                    <th>{t('Path')}</th>
                    <th>{t('Exists')}</th>
                    <th>{t('Source')}</th>
                  </tr>
                </thead>
                <tbody data-testid="directories-table">
                  {status.directories.map((dir) => (
                    <tr key={dir.config_key}>
                      <td>{dir.label}</td>
                      <td className="font-monospace text-break">{dir.path || '—'}</td>
                      <td>
                        <Badge bg={dir.exists ? 'success' : 'danger'}>
                          {dir.exists ? t('Yes') : t('No')}
                        </Badge>
                      </td>
                      <td>
                        <Badge bg={dir.source === 'configured' ? 'primary' : 'secondary'}>
                          {dir.source}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </Card.Body>
          </Card>

          {/* Local Import Status */}
          <Card className="mb-4">
            <Card.Header className="fw-semibold">{t('Local Import Status')}</Card.Header>
            <Card.Body>
              <Row className="g-3">
                <Col md={4}>
                  <div className="text-muted small">{t('Ready')}</div>
                  <Badge bg={status.status.ready ? 'success' : 'warning'} data-testid="import-ready-badge">
                    {status.status.ready ? t('Ready') : t('Not Ready')}
                  </Badge>
                </Col>
                <Col md={4}>
                  <div className="text-muted small">{t('Pending Files')}</div>
                  <div className="fw-semibold">{status.status.pending_files}</div>
                </Col>
                <Col md={4}>
                  <div className="text-muted small">{t('Import Directory')}</div>
                  <div className="font-monospace small text-break">
                    {status.config.import_dir || '—'}
                  </div>
                </Col>
              </Row>
            </Card.Body>
            <Card.Footer>
              <Button
                variant="primary"
                size="sm"
                onClick={handleTriggerImport}
                disabled={importTriggering || !status.status.ready}
                data-testid="trigger-import-btn"
              >
                {importTriggering ? (
                  <><Spinner size="sm" animation="border" className="me-1" />{t('Triggering...')}</>
                ) : (
                  <><i className="fa-solid fa-play me-1" />{t('Trigger Import')}</>
                )}
              </Button>
              {!status.status.ready && (
                <span className="text-muted small ms-3">{t('Directories not ready')}</span>
              )}
            </Card.Footer>
          </Card>
        </>
      ) : null}
    </Container>
  );
};

export default PhotoSettingsPage;

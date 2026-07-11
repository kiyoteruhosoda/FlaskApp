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
import { getApiErrorCode } from '../services/apiErrors';

const PhotoSettingsPage: React.FC = () => {
  const { t } = useTranslation();

  const [status, setStatus] = useState<LocalImportStatusResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadStatus = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiClient.getLocalImportStatus();
      setStatus(data);
    } catch (e: any) {
      setError(getApiErrorCode(e) || e?.message || t('Failed to load settings'));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadStatus();
  }, []);

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

        </>
      ) : null}
    </Container>
  );
};

export default PhotoSettingsPage;

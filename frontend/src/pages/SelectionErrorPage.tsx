import React, { useEffect, useState } from 'react';
import {
  Alert,
  Badge,
  Card,
  Col,
  Container,
  Row,
  Spinner,
  Table,
} from 'react-bootstrap';
import { Link, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../services/api';
import { SelectionErrorPayload } from '../types/api';
import { badgeTextColor, formatDateTime, sessionStatusVariant } from '../utils/format';
import { getApiErrorCode } from '../services/apiErrors';

const LOG_LEVEL_VARIANT: Record<string, string> = {
  ERROR: 'danger',
  WARNING: 'warning',
  INFO: 'info',
  DEBUG: 'secondary',
};

const SelectionErrorPage: React.FC = () => {
  const { t } = useTranslation();
  const { sessionId, selectionId } = useParams<{ sessionId: string; selectionId: string }>();

  const [payload, setPayload] = useState<SelectionErrorPayload | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!sessionId || !selectionId) return;
    setIsLoading(true);
    apiClient
      .getPickerSelectionError(sessionId, parseInt(selectionId, 10))
      .then((data) => setPayload(data))
      .catch((e: any) => setError(getApiErrorCode(e) || e?.message || t('Failed to load error detail')))
      .finally(() => setIsLoading(false));
  }, [sessionId, selectionId, t]);

  if (isLoading) {
    return (
      <Container fluid className="py-5 text-center">
        <Spinner animation="border" />
      </Container>
    );
  }

  return (
    <Container fluid className="py-4" data-testid="selection-error-page">
      <nav aria-label="breadcrumb" className="mb-3">
        <ol className="breadcrumb">
          <li className="breadcrumb-item">
            <Link to="/sessions">{t('Import Sessions')}</Link>
          </li>
          {sessionId && (
            <li className="breadcrumb-item">
              <Link to={`/sessions/${encodeURIComponent(sessionId)}`}>{t('Detail')}</Link>
            </li>
          )}
          <li className="breadcrumb-item active">{t('Import Error')}</li>
        </ol>
      </nav>

      {error && <Alert variant="danger">{error}</Alert>}

      {payload && (
        <>
          <Card className="mb-4">
            <Card.Header>
              <strong>{t('Selection #{{id}}', { id: payload.selection.id })}</strong>
            </Card.Header>
            <Card.Body>
              <Row className="g-3">
                <Col md={4}>
                  <div className="text-muted small">{t('Filename')}</div>
                  <div className="text-break">{payload.selection.filename || payload.selection.googleMediaId || '—'}</div>
                </Col>
                <Col md={2}>
                  <div className="text-muted small">{t('Status')}</div>
                  <Badge bg={sessionStatusVariant(payload.selection.status)} text={badgeTextColor(sessionStatusVariant(payload.selection.status))}>{payload.selection.status}</Badge>
                </Col>
                <Col md={2}>
                  <div className="text-muted small">{t('Attempts')}</div>
                  <div>{payload.selection.attempts}</div>
                </Col>
                <Col md={4}>
                  <div className="text-muted small">{t('Finished')}</div>
                  <div>{formatDateTime(payload.selection.finishedAt)}</div>
                </Col>
                {payload.selection.error && (
                  <Col xs={12}>
                    <div className="text-muted small">{t('Error Message')}</div>
                    <pre className="bg-light p-3 rounded small text-break text-danger" data-testid="error-message">
                      {payload.selection.error}
                    </pre>
                  </Col>
                )}
                {payload.selection.localFilePath && (
                  <Col xs={12}>
                    <div className="text-muted small">{t('Local File Path')}</div>
                    <code className="small">{payload.selection.localFilePath}</code>
                  </Col>
                )}
              </Row>
            </Card.Body>
          </Card>

          {payload.logs && payload.logs.length > 0 && (
            <Card>
              <Card.Header>{t('Related Logs')}</Card.Header>
              <Card.Body className="p-0">
                <Table hover responsive className="mb-0 small font-monospace">
                  <thead>
                    <tr>
                      <th style={{ width: 160 }}>{t('Timestamp')}</th>
                      <th style={{ width: 80 }}>{t('Level')}</th>
                      <th>{t('Message')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {payload.logs.map((log) => (
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
              </Card.Body>
            </Card>
          )}
        </>
      )}
    </Container>
  );
};

export default SelectionErrorPage;

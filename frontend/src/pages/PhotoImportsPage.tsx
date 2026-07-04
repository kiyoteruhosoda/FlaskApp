import React, { useEffect, useRef, useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Container,
  Form,
  ListGroup,
  Row,
  Spinner,
} from 'react-bootstrap';
import { useSelector } from 'react-redux';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { RootState } from '../store';
import { apiClient } from '../services/api';
import {
  LocalImportStatusResponse,
  LocalImportUploadResponse,
  PickerSessionCreateResponse,
} from '../types/api';
import GooglePhotosImportModal from '../components/GooglePhotosImportModal';

const ACCEPTED_EXTENSIONS =
  '.jpg,.jpeg,.png,.tiff,.tif,.bmp,.gif,.webp,.heic,.heif,.mp4,.mov,.avi,.mkv,.m4v,.3gp,.webm';

const PhotoImportsPage: React.FC = () => {
  const { t } = useTranslation();
  const { user } = useSelector((state: RootState) => state.auth);

  const [status, setStatus] = useState<LocalImportStatusResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<LocalImportUploadResponse | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const [importTriggering, setImportTriggering] = useState(false);
  const [importMessage, setImportMessage] = useState<string | null>(null);
  const [importSucceeded, setImportSucceeded] = useState(false);

  // Google フォトからの取り込み
  const [showGoogleImport, setShowGoogleImport] = useState(false);
  const [googleNotice, setGoogleNotice] = useState<{ sessionId: string; pickerUri: string | null } | null>(null);

  const canTriggerImport = user?.permissions?.includes('system:manage') || false;

  const loadStatus = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiClient.getLocalImportStatus();
      setStatus(data);
    } catch (e: any) {
      setError(e?.response?.data?.error || e?.message || t('Failed to load import status'));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadStatus();
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSelectedFiles(Array.from(e.target.files || []));
    setUploadResult(null);
    setUploadError(null);
  };

  const handleUpload = async () => {
    if (selectedFiles.length === 0) return;
    setUploading(true);
    setUploadResult(null);
    setUploadError(null);
    try {
      const result = await apiClient.uploadLocalImportFiles(selectedFiles);
      setUploadResult(result);
      setSelectedFiles([]);
      if (fileInputRef.current) fileInputRef.current.value = '';
      loadStatus();
    } catch (e: any) {
      const data = e?.response?.data;
      if (data?.skipped) {
        setUploadResult(data);
      } else {
        setUploadError(data?.error || e?.message || t('Failed to upload files'));
      }
    } finally {
      setUploading(false);
    }
  };

  const handleTriggerImport = async () => {
    setImportTriggering(true);
    setImportMessage(null);
    try {
      await apiClient.triggerLocalImport();
      setImportSucceeded(true);
      setImportMessage(t('Import triggered successfully'));
      loadStatus();
    } catch (e: any) {
      setImportSucceeded(false);
      setImportMessage(e?.response?.data?.error || e?.message || t('Failed to trigger import'));
    } finally {
      setImportTriggering(false);
    }
  };

  const skippedReasonText = (reason: string): string => {
    switch (reason) {
      case 'unsupported_extension':
        return t('Unsupported file type');
      case 'invalid_filename':
        return t('Invalid file name');
      case 'save_failed':
        return t('Failed to save file');
      default:
        return reason;
    }
  };

  return (
    <Container fluid className="py-4" data-testid="photo-imports-page">
      <Row className="mb-4 align-items-center">
        <Col>
          <h1 className="h3 mb-1">{t('Photo Imports')}</h1>
          <p className="text-muted mb-0">{t('Upload files and import them into the photo library')}</p>
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
          variant={importSucceeded ? 'success' : 'danger'}
          dismissible
          onClose={() => setImportMessage(null)}
          data-testid="import-message"
        >
          {importMessage}
        </Alert>
      )}

      {/* Google フォトから取り込み */}
      <Card className="mb-4" data-testid="google-import-card">
        <Card.Header className="fw-semibold">
          <i className="fa-brands fa-google me-2" />
          {t('Import from Google Photos')}
        </Card.Header>
        <Card.Body>
          <p className="text-muted small mb-3">
            {t('Select photos and videos in Google Photos and import them into the library.')}{' '}
            {t('A linked Google account is required.')}{' '}
            <Link to="/profile#google-accounts">{t('Link a Google account in your profile')}</Link>
          </p>
          {googleNotice && (
            <Alert
              variant="success"
              dismissible
              onClose={() => setGoogleNotice(null)}
              data-testid="google-import-notice"
            >
              {t('Picker session created. Select photos in the opened Google Photos tab.')}{' '}
              {googleNotice.pickerUri && (
                <a href={googleNotice.pickerUri} target="_blank" rel="noopener noreferrer">
                  {t('Open Google Photos Picker')}
                </a>
              )}{' '}
              <Link to={`/sessions/${encodeURIComponent(googleNotice.sessionId)}`}>
                {t('View session progress')}
              </Link>
            </Alert>
          )}
          <Button
            variant="primary"
            size="sm"
            onClick={() => setShowGoogleImport(true)}
            data-testid="google-import-open"
          >
            <i className="fa-brands fa-google me-1" />
            {t('Import from Google Photos')}
          </Button>
        </Card.Body>
      </Card>

      {isLoading && !status ? (
        <div className="text-center py-5"><Spinner animation="border" /></div>
      ) : status ? (
        <>
          {/* Upload */}
          <Card className="mb-4" data-testid="upload-card">
            <Card.Header className="fw-semibold">{t('Upload Files')}</Card.Header>
            <Card.Body>
              <p className="text-muted small mb-3">
                {t('Uploaded files are stored in the import directory and imported on the next run')}
              </p>
              <Form.Group className="mb-3">
                <Form.Control
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept={ACCEPTED_EXTENSIONS}
                  onChange={handleFileChange}
                  disabled={uploading}
                  data-testid="upload-file-input"
                />
              </Form.Group>
              <Button
                variant="primary"
                size="sm"
                onClick={handleUpload}
                disabled={uploading || selectedFiles.length === 0}
                data-testid="upload-btn"
              >
                {uploading ? (
                  <><Spinner size="sm" animation="border" className="me-1" />{t('Uploading...')}</>
                ) : (
                  <><i className="fa-solid fa-upload me-1" />{t('Upload')}</>
                )}
              </Button>
              {selectedFiles.length > 0 && (
                <span className="text-muted small ms-3">
                  {t('{{count}} file(s) selected', { count: selectedFiles.length })}
                </span>
              )}

              {uploadError && (
                <Alert variant="danger" dismissible onClose={() => setUploadError(null)} className="mt-3 mb-0" data-testid="upload-error">
                  {uploadError}
                </Alert>
              )}
              {uploadResult && (
                <div className="mt-3" data-testid="upload-result">
                  {uploadResult.saved.length > 0 && (
                    <Alert variant="success" className="mb-2">
                      {t('{{count}} file(s) uploaded successfully', { count: uploadResult.saved.length })}
                    </Alert>
                  )}
                  {uploadResult.skipped.length > 0 && (
                    <Alert variant="warning" className="mb-0">
                      <div className="mb-1">{t('Some files were skipped')}</div>
                      <ListGroup variant="flush">
                        {uploadResult.skipped.map((item, idx) => (
                          <ListGroup.Item key={`${item.filename}-${idx}`} className="bg-transparent px-0 py-1 border-0 small">
                            <span className="font-monospace">{item.filename}</span>
                            <span className="text-muted ms-2">{skippedReasonText(item.reason)}</span>
                          </ListGroup.Item>
                        ))}
                      </ListGroup>
                    </Alert>
                  )}
                </div>
              )}
            </Card.Body>
          </Card>

          {/* Import Status */}
          <Card className="mb-4" data-testid="import-status-card">
            <Card.Header className="fw-semibold">{t('Import Status')}</Card.Header>
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
                  <div className="fw-semibold" data-testid="pending-files-count">{status.status.pending_files}</div>
                </Col>
                <Col md={4}>
                  <div className="text-muted small">{t('Import Directory')}</div>
                  <div className="font-monospace small text-break">
                    {status.config.import_dir || '—'}
                  </div>
                </Col>
              </Row>
            </Card.Body>
            {canTriggerImport && (
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
            )}
          </Card>
        </>
      ) : null}

      {/* Google フォト取り込みモーダル */}
      <GooglePhotosImportModal
        show={showGoogleImport}
        onHide={() => setShowGoogleImport(false)}
        onCreated={(res: PickerSessionCreateResponse) => {
          setGoogleNotice({
            sessionId: res.sessionId || String(res.pickerSessionId),
            pickerUri: res.pickerUri,
          });
        }}
      />
    </Container>
  );
};

export default PhotoImportsPage;

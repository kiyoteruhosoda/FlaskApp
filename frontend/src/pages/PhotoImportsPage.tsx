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
import GooglePhotosImportStatusCard from '../components/GooglePhotosImportStatusCard';
import { getApiErrorCode } from '../services/apiErrors';

const ACCEPTED_EXTENSIONS =
  '.jpg,.jpeg,.png,.tiff,.tif,.bmp,.gif,.webp,.heic,.heif,.mp4,.mov,.avi,.mkv,.m4v,.3gp,.webm';

const fileKey = (file: File): string => `${file.name}-${file.size}-${file.lastModified}`;

const formatFileSize = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB'];
  let value = bytes / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(1)} ${units[unitIndex]}`;
};

const PhotoImportsPage: React.FC = () => {
  const { t } = useTranslation();
  const { user } = useSelector((state: RootState) => state.auth);

  const [status, setStatus] = useState<LocalImportStatusResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [stagedFiles, setStagedFiles] = useState<File[]>([]);
  const [isDragActive, setIsDragActive] = useState(false);
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
  // セッション作成のたびにステータスカードへ再読込を伝えるトークン
  const [googleStatusReloadToken, setGoogleStatusReloadToken] = useState(0);

  const canTriggerImport = user?.permissions?.includes('system:manage') || false;

  const loadStatus = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiClient.getLocalImportStatus();
      setStatus(data);
    } catch (e: any) {
      setError(getApiErrorCode(e) || e?.message || t('Failed to load import status'));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadStatus();
  }, []);

  const addStagedFiles = (files: File[]) => {
    if (files.length === 0) return;
    setStagedFiles((prev) => {
      const keys = new Set(prev.map(fileKey));
      const additions = files.filter((f) => {
        const k = fileKey(f);
        if (keys.has(k)) return false;
        keys.add(k);
        return true;
      });
      return [...prev, ...additions];
    });
    setUploadResult(null);
    setUploadError(null);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    addStagedFiles(Array.from(e.target.files || []));
    e.target.value = '';
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragActive(true);
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragActive(false);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragActive(false);
    if (uploading) return;
    addStagedFiles(Array.from(e.dataTransfer.files || []));
  };

  const removeStagedFile = (key: string) => {
    setStagedFiles((prev) => prev.filter((f) => fileKey(f) !== key));
  };

  const clearStagedFiles = () => {
    setStagedFiles([]);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleUpload = async () => {
    if (stagedFiles.length === 0) return;
    setUploading(true);
    setUploadResult(null);
    setUploadError(null);
    try {
      const result = await apiClient.uploadLocalImportFiles(stagedFiles);
      setUploadResult(result);
      setStagedFiles([]);
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
      setImportMessage(getApiErrorCode(e) || e?.message || t('Failed to trigger import'));
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

      {/* ===== Google フォト ===== */}
      <h2 className="h6 text-uppercase text-muted fw-bold mb-2" data-testid="google-import-section-title">
        <i className="fa-brands fa-google me-2" />
        {t('Google Photos')}
      </h2>
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

      {/* Google フォト取り込みのステータス（Local Import の Import Status と対） */}
      <GooglePhotosImportStatusCard reloadToken={googleStatusReloadToken} />

      {/* ===== ローカル取り込み ===== */}
      <h2 className="h6 text-uppercase text-muted fw-bold mb-2" data-testid="local-import-section-title">
        <i className="fa-solid fa-desktop me-2" />
        {t('Local Import')}
      </h2>

      {isLoading && !status ? (
        <div className="text-center py-5"><Spinner animation="border" /></div>
      ) : status ? (
        <>
          {/* Upload */}
          <Card className="mb-4" data-testid="upload-card">
            <Card.Header className="fw-semibold">{t('Upload Files')}</Card.Header>
            <Card.Body>
              <div className="text-muted small fw-semibold mb-2">{t('Step 1: Prepare files')}</div>
              <div
                className={`border rounded p-4 text-center mb-3 ${isDragActive ? 'border-primary bg-primary bg-opacity-10' : 'border-secondary-subtle'}`}
                style={{ borderStyle: 'dashed', borderWidth: 2, cursor: uploading ? 'default' : 'pointer' }}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                onClick={() => !uploading && fileInputRef.current?.click()}
                data-testid="upload-dropzone"
              >
                <i className="fa-solid fa-cloud-arrow-up mb-2 d-block" style={{ fontSize: '1.75rem' }} />
                <div className="mb-2">{t('Drag and drop files here, or click to select')}</div>
                <Form.Group onClick={(e) => e.stopPropagation()}>
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
              </div>

              {stagedFiles.length > 0 && (
                <div className="mb-3" data-testid="staged-files">
                  <div className="d-flex justify-content-between align-items-center mb-1">
                    <span className="text-muted small">
                      {t('{{count}} file(s) selected', { count: stagedFiles.length })}
                    </span>
                    <Button
                      variant="link"
                      size="sm"
                      className="p-0 text-decoration-none"
                      onClick={clearStagedFiles}
                      disabled={uploading}
                      data-testid="staged-files-clear"
                    >
                      {t('Clear all')}
                    </Button>
                  </div>
                  <ListGroup variant="flush" className="border rounded">
                    {stagedFiles.map((file) => {
                      const key = fileKey(file);
                      return (
                        <ListGroup.Item
                          key={key}
                          className="d-flex justify-content-between align-items-center py-1 px-2 small"
                          data-testid="staged-file-item"
                        >
                          <span className="text-truncate me-2">
                            <span className="font-monospace">{file.name}</span>{' '}
                            <span className="text-muted">({formatFileSize(file.size)})</span>
                          </span>
                          <Button
                            variant="outline-secondary"
                            size="sm"
                            className="py-0 px-1"
                            onClick={() => removeStagedFile(key)}
                            disabled={uploading}
                            aria-label={t('Remove')}
                            data-testid="staged-file-remove"
                          >
                            <i className="fa-solid fa-xmark" />
                          </Button>
                        </ListGroup.Item>
                      );
                    })}
                  </ListGroup>
                </div>
              )}

              <div className="text-muted small fw-semibold mb-2">{t('Step 2: Execute upload')}</div>
              <Button
                variant="primary"
                size="sm"
                onClick={handleUpload}
                disabled={uploading || stagedFiles.length === 0}
                data-testid="upload-btn"
              >
                {uploading ? (
                  <><Spinner size="sm" animation="border" className="me-1" />{t('Uploading...')}</>
                ) : (
                  <><i className="fa-solid fa-upload me-1" />{t('Upload')}</>
                )}
              </Button>

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
          setGoogleStatusReloadToken((token) => token + 1);
        }}
      />
    </Container>
  );
};

export default PhotoImportsPage;

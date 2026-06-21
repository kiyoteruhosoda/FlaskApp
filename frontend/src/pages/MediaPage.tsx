import React, { useCallback, useEffect, useState } from 'react';
import {
  Container,
  Row,
  Col,
  Card,
  Button,
  Form,
  Spinner,
  Alert,
  Modal,
  Badge,
} from 'react-bootstrap';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../services/api';
import { PhotoItem } from '../types/api';
import { formatDateTime } from '../utils/format';

const MediaPage: React.FC = () => {
  const { t } = useTranslation();

  const [items, setItems] = useState<PhotoItem[]>([]);
  const [thumbs, setThumbs] = useState<Record<number, string>>({});
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasNext, setHasNext] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<'' | 'photo' | 'video'>('');

  const [selected, setSelected] = useState<PhotoItem | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  const loadPage = useCallback(
    async (reset: boolean) => {
      setIsLoading(true);
      setError(null);
      try {
        const params: any = { pageSize: 24 };
        if (typeFilter) params.is_video = typeFilter === 'video' ? 1 : 0;
        if (!reset && cursor) params.cursor = cursor;
        const data = await apiClient.getPhotos(params);
        const next = data.items || [];
        setItems((prev) => (reset ? next : [...prev, ...next]));
        setHasNext(Boolean(data.hasNext));
        setCursor(data.nextCursor ?? null);
      } catch (e: any) {
        setError(e?.response?.data?.error || e?.message || t('Failed to load media'));
      } finally {
        setIsLoading(false);
      }
    },
    [cursor, typeFilter, t]
  );

  // フィルタ変更時はリセットして再読込
  useEffect(() => {
    setItems([]);
    setCursor(null);
    loadPage(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [typeFilter]);

  // 表示中アイテムのサムネ署名URLを取得
  useEffect(() => {
    let cancelled = false;
    const missing = items.filter((m) => !thumbs[m.id]);
    if (missing.length === 0) return;
    (async () => {
      for (const m of missing) {
        try {
          const url = await apiClient.getPhotoThumbUrl(m.id, 256);
          if (!cancelled && url) {
            setThumbs((prev) => ({ ...prev, [m.id]: url }));
          }
        } catch {
          /* サムネ取得失敗は無視 */
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [items, thumbs]);

  const openDetail = async (media: PhotoItem) => {
    setSelected(media);
    setPreviewUrl(null);
    try {
      const url = await apiClient.getPhotoThumbUrl(media.id, 1024);
      setPreviewUrl(url);
    } catch {
      /* ignore */
    }
  };

  return (
    <Container fluid className="py-4" data-testid="media-page">
      <Row className="mb-3">
        <Col>
          <h1 className="h3 mb-1">{t('Media Gallery')}</h1>
          <p className="text-muted mb-0">{t('Browse imported photos and videos')}</p>
        </Col>
        <Col xs="auto">
          <Form.Select
            value={typeFilter}
            data-testid="media-type-filter"
            onChange={(e) => setTypeFilter(e.target.value as '' | 'photo' | 'video')}
            style={{ width: 160 }}
          >
            <option value="">{t('All')}</option>
            <option value="photo">{t('Photos')}</option>
            <option value="video">{t('Videos')}</option>
          </Form.Select>
        </Col>
      </Row>

      {error && (
        <Alert variant="danger" dismissible onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {items.length === 0 && !isLoading ? (
        <div className="text-center text-muted py-5" data-testid="media-empty">
          {t('No media found')}
        </div>
      ) : (
        <Row xs={2} sm={3} md={4} lg={6} className="g-3">
          {items.map((m) => (
            <Col key={m.id}>
              <Card
                className="h-100 media-card"
                role="button"
                onClick={() => openDetail(m)}
                data-testid="media-card"
              >
                <div
                  className="ratio ratio-1x1 bg-light d-flex align-items-center justify-content-center"
                  style={{ overflow: 'hidden' }}
                >
                  {thumbs[m.id] ? (
                    <img
                      src={thumbs[m.id]}
                      alt={m.filename || String(m.id)}
                      style={{ objectFit: 'cover', width: '100%', height: '100%' }}
                    />
                  ) : (
                    <i className="bi bi-image text-muted fs-2" />
                  )}
                </div>
                <Card.Body className="p-2">
                  <div className="small text-truncate">{m.filename || `#${m.id}`}</div>
                  {Boolean(m.is_video) && (
                    <Badge bg="dark" className="mt-1">
                      <i className="bi bi-play-fill" /> {t('Video')}
                    </Badge>
                  )}
                </Card.Body>
              </Card>
            </Col>
          ))}
        </Row>
      )}

      <div className="text-center mt-4">
        {isLoading ? (
          <Spinner animation="border" />
        ) : hasNext ? (
          <Button variant="outline-primary" onClick={() => loadPage(false)} data-testid="media-load-more">
            {t('Load more')}
          </Button>
        ) : null}
      </div>

      <Modal show={!!selected} onHide={() => setSelected(null)} size="lg" centered>
        <Modal.Header closeButton>
          <Modal.Title className="text-truncate">
            {selected?.filename || (selected ? `#${selected.id}` : '')}
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {selected && (
            <>
              <div className="text-center mb-3 bg-light" style={{ minHeight: 200 }}>
                {previewUrl ? (
                  <img
                    src={previewUrl}
                    alt={selected.filename || String(selected.id)}
                    style={{ maxWidth: '100%', maxHeight: 480 }}
                    data-testid="media-preview"
                  />
                ) : (
                  <div className="py-5">
                    <Spinner animation="border" />
                  </div>
                )}
              </div>
              <dl className="row mb-2 small">
                <dt className="col-sm-3">{t('Shot at')}</dt>
                <dd className="col-sm-9">{formatDateTime(selected.shot_at)}</dd>
                <dt className="col-sm-3">{t('Dimensions')}</dt>
                <dd className="col-sm-9">
                  {selected.width && selected.height
                    ? `${selected.width} × ${selected.height}`
                    : '—'}
                </dd>
                <dt className="col-sm-3">{t('Camera')}</dt>
                <dd className="col-sm-9">
                  {[selected.camera_make, selected.camera_model]
                    .filter(Boolean)
                    .join(' ') || '—'}
                </dd>
                <dt className="col-sm-3">{t('Source')}</dt>
                <dd className="col-sm-9">{selected.source_label || '—'}</dd>
              </dl>
              <div>
                <span className="me-2 small text-muted">{t('Tags')}:</span>
                {selected.tags.length === 0 ? (
                  <span className="text-muted small">—</span>
                ) : (
                  selected.tags.map((tag) => (
                    <Badge bg="secondary" key={tag.id} className="me-1">
                      {tag.name}
                    </Badge>
                  ))
                )}
              </div>
            </>
          )}
        </Modal.Body>
      </Modal>
    </Container>
  );
};

export default MediaPage;

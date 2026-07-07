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
import { PhotoItem, MediaTag } from '../types/api';
import { formatDateTime } from '../utils/format';
import MediaSearchBar, {
  EMPTY_MEDIA_SEARCH_FILTERS,
  MediaSearchFilters,
  toMediaQueryParams,
} from '../components/MediaSearchBar';

const MediaPage: React.FC = () => {
  const { t } = useTranslation();

  const [items, setItems] = useState<PhotoItem[]>([]);
  const [thumbs, setThumbs] = useState<Record<number, string>>({});
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasNext, setHasNext] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 検索条件（タグ・撮影日時・メディア種別）
  const [filters, setFilters] = useState<MediaSearchFilters>(EMPTY_MEDIA_SEARCH_FILTERS);

  // detail modal state
  const [selected, setSelected] = useState<PhotoItem | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [playbackUrl, setPlaybackUrl] = useState<string | null>(null);
  const [mediaLoading, setMediaLoading] = useState(false);

  // tag edit state
  const [editingTags, setEditingTags] = useState(false);
  const [allTags, setAllTags] = useState<MediaTag[]>([]);
  const [selectedTagIds, setSelectedTagIds] = useState<number[]>([]);
  const [savingTags, setSavingTags] = useState(false);
  const [tagError, setTagError] = useState<string | null>(null);

  const loadPage = useCallback(
    async (reset: boolean) => {
      setIsLoading(true);
      setError(null);
      try {
        const params: any = { pageSize: 24, ...toMediaQueryParams(filters) };
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
    [cursor, filters, t]
  );

  useEffect(() => {
    setItems([]);
    setCursor(null);
    loadPage(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters]);

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
    return () => { cancelled = true; };
  }, [items, thumbs]);

  const openDetail = async (media: PhotoItem) => {
    setSelected(media);
    setPreviewUrl(null);
    setPlaybackUrl(null);
    setEditingTags(false);
    setSelectedTagIds(media.tags.map((t) => t.id));
    setTagError(null);
    setMediaLoading(true);
    try {
      if (media.is_video && media.has_playback) {
        const url = await apiClient.getPhotoPlaybackUrl(media.id);
        setPlaybackUrl(url);
      } else {
        const url = await apiClient.getPhotoThumbUrl(media.id, 1024);
        setPreviewUrl(url);
      }
    } catch {
      /* ignore */
    } finally {
      setMediaLoading(false);
    }
  };

  const startEditTags = async () => {
    if (allTags.length === 0) {
      try {
        const data = await apiClient.getTags({ limit: 100 });
        setAllTags(data.items);
      } catch {
        /* ignore */
      }
    }
    setEditingTags(true);
    setTagError(null);
  };

  const toggleTag = (tagId: number) => {
    setSelectedTagIds((prev) =>
      prev.includes(tagId) ? prev.filter((id) => id !== tagId) : [...prev, tagId]
    );
  };

  const saveTags = async () => {
    if (!selected) return;
    setSavingTags(true);
    setTagError(null);
    try {
      const result = await apiClient.updateMediaTags(selected.id, selectedTagIds);
      const updatedMedia = { ...selected, tags: result.tags };
      setSelected(updatedMedia);
      setItems((prev) => prev.map((m) => (m.id === selected.id ? updatedMedia : m)));
      setEditingTags(false);
    } catch (e: any) {
      setTagError(e?.response?.data?.message || e?.message || t('Failed to save tags'));
    } finally {
      setSavingTags(false);
    }
  };

  const closeDetail = () => {
    setSelected(null);
    setEditingTags(false);
  };

  return (
    <Container fluid className="py-4" data-testid="media-page">
      <Row className="mb-3">
        <Col>
          <h1 className="h3 mb-1">{t('Media Gallery')}</h1>
          <p className="text-muted mb-0">{t('Browse imported photos and videos')}</p>
        </Col>
      </Row>

      {/* 検索: タグ・撮影日時・メディア種別 */}
      <div className="border rounded p-3 mb-3 bg-body-tertiary">
        <MediaSearchBar filters={filters} onChange={setFilters} />
      </div>

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
        <Row xs={3} sm={4} md={6} lg={8} xl={10} className="g-2">
          {items.map((m) => (
            <Col key={m.id}>
              <Card
                className="h-100 media-card"
                role="button"
                onClick={() => openDetail(m)}
                data-testid="media-card"
              >
                <div
                  className="ratio ratio-1x1 bg-light d-flex align-items-center justify-content-center position-relative"
                  style={{ overflow: 'hidden' }}
                >
                  {thumbs[m.id] ? (
                    <img
                      src={thumbs[m.id]}
                      alt={m.filename || String(m.id)}
                      style={{ objectFit: 'cover', width: '100%', height: '100%' }}
                    />
                  ) : (
                    <i className="fa-solid fa-image text-muted fs-2" />
                  )}
                  {Boolean(m.is_video) && (
                    <div className="position-absolute top-50 start-50 translate-middle">
                      <i className="fa-solid fa-circle-play text-white fs-3" style={{ textShadow: '0 0 4px #000' }} />
                    </div>
                  )}
                </div>
                <Card.Body className="p-2">
                  <div className="small text-truncate">{m.filename || `#${m.id}`}</div>
                  {Boolean(m.is_video) && (
                    <Badge bg="dark" className="mt-1">
                      <i className="fa-solid fa-play" /> {t('Video')}
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

      {/* Detail Modal */}
      <Modal show={!!selected} onHide={closeDetail} size="lg" centered>
        <Modal.Header closeButton>
          <Modal.Title className="text-truncate">
            {selected?.filename || (selected ? `#${selected.id}` : '')}
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {selected && (
            <>
              {/* Media preview */}
              <div className="text-center mb-3 bg-light" style={{ minHeight: 200 }}>
                {mediaLoading ? (
                  <div className="py-5"><Spinner animation="border" /></div>
                ) : selected.is_video ? (
                  playbackUrl ? (
                    <video
                      controls
                      src={playbackUrl}
                      style={{ maxWidth: '100%', maxHeight: 480 }}
                      data-testid="media-video"
                    />
                  ) : (
                    <div className="py-5 text-muted">
                      <i className="fa-solid fa-circle-play fs-1 d-block mb-2" />
                      {t('Video not available')}
                    </div>
                  )
                ) : previewUrl ? (
                  <img
                    src={previewUrl}
                    alt={selected.filename || String(selected.id)}
                    style={{ maxWidth: '100%', maxHeight: 480 }}
                    data-testid="media-preview"
                  />
                ) : (
                  <div className="py-5"><Spinner animation="border" /></div>
                )}
              </div>

              {/* Metadata */}
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
                  {[selected.camera_make, selected.camera_model].filter(Boolean).join(' ') || '—'}
                </dd>
                <dt className="col-sm-3">{t('Source')}</dt>
                <dd className="col-sm-9">{selected.source_label || '—'}</dd>
              </dl>

              {/* Tags section */}
              <div className="border-top pt-2">
                {!editingTags ? (
                  <div className="d-flex align-items-center gap-2 flex-wrap">
                    <span className="small text-muted">{t('Tags')}:</span>
                    {selected.tags.length === 0 ? (
                      <span className="text-muted small">—</span>
                    ) : (
                      selected.tags.map((tag) => (
                        <Badge bg="secondary" key={tag.id}>
                          {tag.name}
                        </Badge>
                      ))
                    )}
                    <Button
                      size="sm"
                      variant="outline-secondary"
                      onClick={startEditTags}
                      data-testid="media-edit-tags"
                    >
                      <i className="fa-solid fa-tag me-1" />{t('Edit Tags')}
                    </Button>
                  </div>
                ) : (
                  <div>
                    <div className="small fw-semibold mb-2">{t('Select tags')}:</div>
                    {tagError && <Alert variant="danger" className="py-1 px-2 small">{tagError}</Alert>}
                    {allTags.length === 0 ? (
                      <div className="text-muted small">{t('No tags available')}</div>
                    ) : (
                      <div className="d-flex flex-wrap gap-2 mb-2">
                        {allTags.map((tag) => (
                          <Form.Check
                            key={tag.id}
                            type="checkbox"
                            id={`tag-${tag.id}`}
                            label={tag.attr ? `${tag.name} (${tag.attr})` : tag.name}
                            checked={selectedTagIds.includes(tag.id)}
                            onChange={() => toggleTag(tag.id)}
                            data-testid="tag-checkbox"
                          />
                        ))}
                      </div>
                    )}
                    <div className="d-flex gap-2">
                      <Button
                        size="sm"
                        variant="primary"
                        onClick={saveTags}
                        disabled={savingTags}
                        data-testid="save-tags"
                      >
                        {savingTags ? <Spinner size="sm" animation="border" /> : t('Save Tags')}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline-secondary"
                        onClick={() => setEditingTags(false)}
                      >
                        {t('Cancel')}
                      </Button>
                    </div>
                  </div>
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

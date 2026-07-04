import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Badge, Button, Card, Col, Modal, Row, Spinner } from 'react-bootstrap';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../services/api';
import { PhotoItem } from '../types/api';
import MediaSearchBar, {
  EMPTY_MEDIA_SEARCH_FILTERS,
  MediaSearchFilters,
  toMediaQueryParams,
} from './MediaSearchBar';

interface MediaPickerModalProps {
  show: boolean;
  onHide: () => void;
  // 選択確定時に呼ばれる。成功時はモーダルを閉じる。
  onSubmit: (mediaIds: number[]) => Promise<void>;
  // 既に対象へ含まれているため選択不可にするメディア ID
  excludeIds?: number[];
  title?: string;
  submitLabel?: string;
}

// メディア検索（タグ・撮影日時・種別）付きの複数選択モーダル。
// アルバムへのメディア追加などで使う。
const MediaPickerModal: React.FC<MediaPickerModalProps> = ({
  show,
  onHide,
  onSubmit,
  excludeIds = [],
  title,
  submitLabel,
}) => {
  const { t } = useTranslation();

  const [filters, setFilters] = useState<MediaSearchFilters>(EMPTY_MEDIA_SEARCH_FILTERS);
  const [items, setItems] = useState<PhotoItem[]>([]);
  const [thumbs, setThumbs] = useState<Record<number, string>>({});
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasNext, setHasNext] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [submitting, setSubmitting] = useState(false);

  const excluded = new Set(excludeIds);

  const loadPage = useCallback(
    async (reset: boolean, currentCursor: string | null) => {
      setIsLoading(true);
      setError(null);
      try {
        const params: any = { pageSize: 24, ...toMediaQueryParams(filters) };
        if (!reset && currentCursor) params.cursor = currentCursor;
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
    [filters, t]
  );

  // モーダルを開いたとき・検索条件変更時に最初のページを読み込む
  useEffect(() => {
    if (!show) return;
    setItems([]);
    setCursor(null);
    loadPage(true, null);
  }, [show, loadPage]);

  // モーダルを閉じたら選択状態をリセット
  useEffect(() => {
    if (!show) {
      setSelectedIds([]);
      setFilters(EMPTY_MEDIA_SEARCH_FILTERS);
      setError(null);
    }
  }, [show]);

  // サムネイル URL を遅延取得
  useEffect(() => {
    if (!show) return;
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
  }, [show, items, thumbs]);

  const toggleSelect = (media: PhotoItem) => {
    if (excluded.has(media.id)) return;
    setSelectedIds((prev) =>
      prev.includes(media.id) ? prev.filter((id) => id !== media.id) : [...prev, media.id]
    );
  };

  const handleSubmit = async () => {
    if (selectedIds.length === 0) return;
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit(selectedIds);
      onHide();
    } catch (e: any) {
      setError(
        e?.response?.data?.message || e?.response?.data?.error || e?.message || t('Failed to add media')
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal show={show} onHide={onHide} size="xl" centered scrollable data-testid="media-picker-modal">
      <Modal.Header closeButton>
        <Modal.Title>{title || t('Select Media')}</Modal.Title>
      </Modal.Header>
      <Modal.Body>
        {error && (
          <Alert variant="danger" dismissible onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        {/* メディア検索 */}
        <div className="border rounded p-3 mb-3 bg-body-tertiary">
          <MediaSearchBar filters={filters} onChange={setFilters} />
        </div>

        {items.length === 0 && !isLoading ? (
          <div className="text-center text-muted py-5" data-testid="media-picker-empty">
            {t('No media found')}
          </div>
        ) : (
          <Row xs={3} sm={4} md={6} className="g-2">
            {items.map((m) => {
              const isExcluded = excluded.has(m.id);
              const isSelected = selectedIds.includes(m.id);
              return (
                <Col key={m.id}>
                  <Card
                    className={`h-100 ${isSelected ? 'border-primary border-2' : ''}`}
                    role="button"
                    onClick={() => toggleSelect(m)}
                    style={{ opacity: isExcluded ? 0.4 : 1, cursor: isExcluded ? 'not-allowed' : 'pointer' }}
                    data-testid="media-picker-card"
                    aria-selected={isSelected}
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
                        <i className="fa-solid fa-image text-muted fs-3" />
                      )}
                      {Boolean(m.is_video) && (
                        <div className="position-absolute top-50 start-50 translate-middle">
                          <i className="fa-solid fa-circle-play text-white fs-4" style={{ textShadow: '0 0 4px #000' }} />
                        </div>
                      )}
                      {isSelected && (
                        <div className="position-absolute top-0 end-0 m-1">
                          <i className="fa-solid fa-circle-check text-primary fs-5 bg-white rounded-circle" />
                        </div>
                      )}
                      {isExcluded && (
                        <div className="position-absolute top-0 start-0 m-1">
                          <Badge bg="secondary">{t('Already added')}</Badge>
                        </div>
                      )}
                    </div>
                    <Card.Body className="p-1">
                      <div className="small text-truncate">{m.filename || `#${m.id}`}</div>
                    </Card.Body>
                  </Card>
                </Col>
              );
            })}
          </Row>
        )}

        <div className="text-center mt-3">
          {isLoading ? (
            <Spinner animation="border" />
          ) : hasNext ? (
            <Button
              variant="outline-primary"
              size="sm"
              onClick={() => loadPage(false, cursor)}
              data-testid="media-picker-load-more"
            >
              {t('Load more')}
            </Button>
          ) : null}
        </div>
      </Modal.Body>
      <Modal.Footer className="justify-content-between">
        <span className="text-muted small" data-testid="media-picker-selected-count">
          {t('{{count}} selected', { count: selectedIds.length })}
        </span>
        <div className="d-flex gap-2">
          <Button variant="secondary" onClick={onHide}>{t('Cancel')}</Button>
          <Button
            variant="primary"
            onClick={handleSubmit}
            disabled={submitting || selectedIds.length === 0}
            data-testid="media-picker-submit"
          >
            {submitting ? (
              <><Spinner size="sm" animation="border" className="me-1" />{t('Adding...')}</>
            ) : (
              submitLabel || t('Add Selected')
            )}
          </Button>
        </div>
      </Modal.Footer>
    </Modal>
  );
};

export default MediaPickerModal;

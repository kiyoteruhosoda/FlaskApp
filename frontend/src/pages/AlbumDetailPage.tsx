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
  Badge,
  Modal,
} from 'react-bootstrap';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../services/api';
import { AlbumDetail, AlbumMediaItem } from '../types/api';
import MediaPickerModal from '../components/MediaPickerModal';

const VISIBILITY_OPTIONS = ['private', 'unlisted', 'public'] as const;

const AlbumDetailPage: React.FC = () => {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const albumId = Number(id);
  const navigate = useNavigate();

  const [album, setAlbum] = useState<AlbumDetail | null>(null);
  const [thumbs, setThumbs] = useState<Record<number, string>>({});
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // edit modal
  const [showEdit, setShowEdit] = useState(false);
  const [editForm, setEditForm] = useState({ name: '', description: '', visibility: 'private' });
  const [editError, setEditError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // delete confirm
  const [showDelete, setShowDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  // reorder mode
  const [isReordering, setIsReordering] = useState(false);
  const [orderedMedia, setOrderedMedia] = useState<AlbumMediaItem[]>([]);
  const [savingOrder, setSavingOrder] = useState(false);
  const [dragIdx, setDragIdx] = useState<number | null>(null);

  // add media modal
  const [showAddMedia, setShowAddMedia] = useState(false);

  // cover selection
  const [settingCoverId, setSettingCoverId] = useState<number | null>(null);

  const loadAlbum = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiClient.getAlbumDetail(albumId);
      setAlbum(data.album);
      setOrderedMedia(data.album.media);
    } catch (e: any) {
      setError(e?.response?.data?.message || e?.message || t('Failed to load album'));
    } finally {
      setIsLoading(false);
    }
  }, [albumId, t]);

  useEffect(() => {
    loadAlbum();
  }, [loadAlbum]);

  // fetch signed thumbnail URLs lazily
  useEffect(() => {
    let cancelled = false;
    const missing = orderedMedia.filter((m) => !thumbs[m.id]);
    if (missing.length === 0) return;
    (async () => {
      for (const m of missing) {
        try {
          const url = await apiClient.getPhotoThumbUrl(m.id, 256);
          if (!cancelled && url) {
            setThumbs((prev) => ({ ...prev, [m.id]: url }));
          }
        } catch {
          /* ignore */
        }
      }
    })();
    return () => { cancelled = true; };
  }, [orderedMedia, thumbs]);

  const openEdit = () => {
    if (!album) return;
    setEditForm({ name: album.title, description: album.description || '', visibility: album.visibility || 'private' });
    setEditError(null);
    setShowEdit(true);
  };

  const submitEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editForm.name.trim()) {
      setEditError(t('Album name is required'));
      return;
    }
    setSaving(true);
    setEditError(null);
    try {
      const res = await apiClient.updateAlbumItem(albumId, {
        name: editForm.name.trim(),
        description: editForm.description.trim() || undefined,
        visibility: editForm.visibility,
      });
      setAlbum(res.album);
      setOrderedMedia(res.album.media);
      setShowEdit(false);
    } catch (e: any) {
      setEditError(e?.response?.data?.message || e?.response?.data?.error || e?.message || t('Failed to save album'));
    } finally {
      setSaving(false);
    }
  };

  const confirmDelete = async () => {
    setDeleting(true);
    try {
      await apiClient.deleteAlbumItem(albumId);
      navigate('/albums');
    } catch (e: any) {
      setError(e?.response?.data?.message || e?.message || t('Failed to delete album'));
      setShowDelete(false);
    } finally {
      setDeleting(false);
    }
  };

  const startReorder = () => {
    setIsReordering(true);
    setDragIdx(null);
  };

  const cancelReorder = () => {
    setIsReordering(false);
    if (album) setOrderedMedia(album.media);
  };

  const handleDragStart = (idx: number) => setDragIdx(idx);

  const handleDragOver = (e: React.DragEvent) => e.preventDefault();

  const handleDrop = (e: React.DragEvent, idx: number) => {
    e.preventDefault();
    if (dragIdx === null || dragIdx === idx) return;
    const updated = [...orderedMedia];
    const [item] = updated.splice(dragIdx, 1);
    updated.splice(idx, 0, item);
    setOrderedMedia(updated);
    setDragIdx(null);
  };

  // 検索モーダルで選択したメディアをアルバム末尾に追加する
  const handleAddMedia = async (mediaIds: number[]) => {
    if (!album) return;
    const currentIds = orderedMedia.map((m) => m.id);
    const merged = [...currentIds, ...mediaIds.filter((id) => !currentIds.includes(id))];
    const res = await apiClient.updateAlbumItem(albumId, { mediaIds: merged });
    setAlbum(res.album);
    setOrderedMedia(res.album.media);
  };

  // 表紙（カバー画像）を選択する
  const handleSetCover = async (mediaId: number) => {
    setSettingCoverId(mediaId);
    setError(null);
    try {
      const res = await apiClient.updateAlbumItem(albumId, { coverMediaId: mediaId });
      setAlbum(res.album);
      setOrderedMedia(res.album.media);
    } catch (e: any) {
      setError(e?.response?.data?.message || e?.message || t('Failed to set cover'));
    } finally {
      setSettingCoverId(null);
    }
  };

  const saveOrder = async () => {
    setSavingOrder(true);
    try {
      const newIds = orderedMedia.map((m) => m.id);
      const res = await apiClient.reorderAlbumMedia(albumId, newIds);
      setAlbum(res.album);
      setOrderedMedia(res.album.media);
      setIsReordering(false);
    } catch (e: any) {
      setError(e?.response?.data?.message || e?.message || t('Failed to reorder media'));
    } finally {
      setSavingOrder(false);
    }
  };

  if (isLoading) {
    return (
      <div className="text-center py-5">
        <Spinner animation="border" />
      </div>
    );
  }

  if (!album && !isLoading) {
    return (
      <Container className="py-4">
        <Alert variant="danger">{error || t('Album not found')}</Alert>
        <Link to="/albums">{t('Back to Albums')}</Link>
      </Container>
    );
  }

  return (
    <Container fluid className="py-4" data-testid="album-detail-page">
      {error && (
        <Alert variant="danger" dismissible onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {album && (
        <>
          {/* Header */}
          <Row className="mb-4 align-items-start">
            <Col>
              <div className="d-flex align-items-center gap-2 mb-1">
                <Link to="/albums" className="text-muted text-decoration-none">
                  <i className="fa-solid fa-arrow-left" />
                </Link>
                <h1 className="h3 mb-0">{album.title}</h1>
                {album.visibility && (
                  <Badge bg="secondary" className="text-capitalize">{album.visibility}</Badge>
                )}
              </div>
              {album.description && (
                <p className="text-muted mb-0">{album.description}</p>
              )}
              <small className="text-muted">
                {t('{{count}} items', { count: album.mediaCount })}
              </small>
            </Col>
            <Col xs="auto" className="d-flex gap-2">
              {isReordering ? (
                <>
                  <Button variant="outline-secondary" onClick={cancelReorder}>
                    {t('Cancel')}
                  </Button>
                  <Button variant="primary" onClick={saveOrder} disabled={savingOrder}>
                    {savingOrder ? <Spinner size="sm" animation="border" /> : t('Save Order')}
                  </Button>
                </>
              ) : (
                <>
                  <Button
                    variant="primary"
                    onClick={() => setShowAddMedia(true)}
                    data-testid="album-add-media"
                  >
                    <i className="fa-solid fa-plus me-1" />{t('Add Media')}
                  </Button>
                  {album.mediaCount > 0 && (
                    <Link
                      to={`/albums/${album.id}/slideshow`}
                      className="btn btn-outline-secondary"
                      data-testid="album-slideshow"
                    >
                      <i className="fa-solid fa-circle-play me-1" />{t('Slideshow')}
                    </Link>
                  )}
                  {album.mediaCount > 1 && (
                    <Button variant="outline-secondary" onClick={startReorder} data-testid="album-reorder">
                      <i className="fa-solid fa-arrow-down-up-across-line me-1" />{t('Reorder')}
                    </Button>
                  )}
                  <Button variant="outline-primary" onClick={openEdit} data-testid="album-edit">
                    <i className="fa-solid fa-pen me-1" />{t('Edit')}
                  </Button>
                  <Button variant="outline-danger" onClick={() => setShowDelete(true)} data-testid="album-delete">
                    <i className="fa-solid fa-trash me-1" />{t('Delete')}
                  </Button>
                </>
              )}
            </Col>
          </Row>

          {/* Reorder hint */}
          {isReordering && (
            <Alert variant="info" className="mb-3">
              {t('Drag and drop to reorder media, then click Save Order.')}
            </Alert>
          )}

          {/* Media Grid */}
          {orderedMedia.length === 0 ? (
            <div className="text-center text-muted py-5" data-testid="album-empty">
              <p>{t('No media in this album')}</p>
              <Button variant="outline-primary" onClick={() => setShowAddMedia(true)}>
                <i className="fa-solid fa-plus me-1" />{t('Add Media')}
              </Button>
            </div>
          ) : (
            <Row xs={3} sm={4} md={6} lg={8} className="g-2">
              {orderedMedia.map((m, idx) => (
                <Col key={m.id}>
                  <Card
                    className="h-100"
                    draggable={isReordering}
                    onDragStart={isReordering ? () => handleDragStart(idx) : undefined}
                    onDragOver={isReordering ? handleDragOver : undefined}
                    onDrop={isReordering ? (e) => handleDrop(e, idx) : undefined}
                    style={{
                      cursor: isReordering ? 'grab' : 'default',
                      opacity: dragIdx === idx ? 0.5 : 1,
                      border: dragIdx !== null && dragIdx !== idx && isReordering ? '2px dashed #0d6efd' : undefined,
                    }}
                    data-testid="album-media-card"
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
                          draggable={false}
                        />
                      ) : (
                        <i className="fa-solid fa-image text-muted fs-2" />
                      )}
                      {album.coverMediaId === m.id && (
                        <div className="position-absolute top-0 start-0 m-1">
                          <Badge bg="warning" text="dark" data-testid="album-cover-badge">
                            <i className="fa-solid fa-star me-1" />{t('Cover')}
                          </Badge>
                        </div>
                      )}
                      {!isReordering && album.coverMediaId !== m.id && thumbs[m.id] && (
                        <div className="position-absolute top-0 end-0 m-1">
                          <Button
                            variant="light"
                            size="sm"
                            className="py-0 px-1 border"
                            title={t('Set as cover')}
                            disabled={settingCoverId !== null}
                            onClick={(e) => {
                              e.stopPropagation();
                              handleSetCover(m.id);
                            }}
                            data-testid="album-set-cover"
                          >
                            {settingCoverId === m.id ? (
                              <Spinner size="sm" animation="border" />
                            ) : (
                              <i className="fa-regular fa-star" />
                            )}
                          </Button>
                        </div>
                      )}
                    </div>
                    <Card.Body className="p-2">
                      <div className="small text-truncate">{m.filename || `#${m.id}`}</div>
                      {m.tags.length > 0 && (
                        <div className="d-flex flex-wrap gap-1 mt-1">
                          {m.tags.map((tag) => (
                            <Badge key={tag.id} bg="light" text="dark" className="border small">
                              {tag.name}
                            </Badge>
                          ))}
                        </div>
                      )}
                    </Card.Body>
                  </Card>
                </Col>
              ))}
            </Row>
          )}
        </>
      )}

      {/* Add Media Modal（メディア検索 + 複数選択） */}
      <MediaPickerModal
        show={showAddMedia}
        onHide={() => setShowAddMedia(false)}
        onSubmit={handleAddMedia}
        excludeIds={orderedMedia.map((m) => m.id)}
        title={t('Add media to "{{name}}"', { name: album?.title })}
        submitLabel={t('Add to Album')}
      />

      {/* Edit Modal */}
      <Modal show={showEdit} onHide={() => setShowEdit(false)} centered>
        <Form onSubmit={submitEdit}>
          <Modal.Header closeButton>
            <Modal.Title>{t('Edit Album')}</Modal.Title>
          </Modal.Header>
          <Modal.Body>
            {editError && <Alert variant="danger">{editError}</Alert>}
            <Form.Group className="mb-3">
              <Form.Label>{t('Album name')}</Form.Label>
              <Form.Control
                type="text"
                value={editForm.name}
                onChange={(e) => setEditForm((f) => ({ ...f, name: e.target.value }))}
                required
                autoFocus
              />
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>{t('Description')}</Form.Label>
              <Form.Control
                as="textarea"
                rows={2}
                value={editForm.description}
                onChange={(e) => setEditForm((f) => ({ ...f, description: e.target.value }))}
              />
            </Form.Group>
            <Form.Group>
              <Form.Label>{t('Visibility')}</Form.Label>
              <Form.Select
                value={editForm.visibility}
                onChange={(e) => setEditForm((f) => ({ ...f, visibility: e.target.value }))}
              >
                {VISIBILITY_OPTIONS.map((v) => (
                  <option key={v} value={v}>{t(`visibility_${v}`)}</option>
                ))}
              </Form.Select>
            </Form.Group>
          </Modal.Body>
          <Modal.Footer>
            <Button variant="secondary" onClick={() => setShowEdit(false)}>{t('Cancel')}</Button>
            <Button type="submit" variant="primary" disabled={saving}>
              {saving ? <Spinner size="sm" animation="border" /> : t('Save')}
            </Button>
          </Modal.Footer>
        </Form>
      </Modal>

      {/* Delete Confirm Modal */}
      <Modal show={showDelete} onHide={() => setShowDelete(false)} centered>
        <Modal.Header closeButton>
          <Modal.Title>{t('Delete Album')}</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {t('Delete album "{{name}}"?', { name: album?.title })}
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setShowDelete(false)}>{t('Cancel')}</Button>
          <Button variant="danger" onClick={confirmDelete} disabled={deleting}>
            {deleting ? <Spinner size="sm" animation="border" /> : t('Delete')}
          </Button>
        </Modal.Footer>
      </Modal>
    </Container>
  );
};

export default AlbumDetailPage;

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
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../services/api';
import { AlbumSummary } from '../types/api';
import { getApiErrorCode } from '../services/apiErrors';

const VISIBILITY_OPTIONS = ['private', 'unlisted', 'public'] as const;

interface AlbumFormState {
  name: string;
  description: string;
  visibility: string;
}

const defaultForm = (): AlbumFormState => ({ name: '', description: '', visibility: 'private' });

const AlbumsPage: React.FC = () => {
  const { t } = useTranslation();

  const [albums, setAlbums] = useState<AlbumSummary[]>([]);
  const [covers, setCovers] = useState<Record<number, string>>({});
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasNext, setHasNext] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');

  // create/edit modal
  const [showForm, setShowForm] = useState(false);
  const [editTarget, setEditTarget] = useState<AlbumSummary | null>(null);
  const [form, setForm] = useState<AlbumFormState>(defaultForm());
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // delete confirm
  const [deleteTarget, setDeleteTarget] = useState<AlbumSummary | null>(null);
  const [deleting, setDeleting] = useState(false);

  const loadPage = useCallback(
    async (reset: boolean) => {
      setIsLoading(true);
      setError(null);
      try {
        const params: any = { pageSize: 24 };
        if (query) params.q = query;
        if (!reset && cursor) params.cursor = cursor;
        const data = await apiClient.getAlbums(params);
        const next = data.items || [];
        setAlbums((prev) => (reset ? next : [...prev, ...next]));
        setHasNext(Boolean(data.hasNext));
        setCursor(data.nextCursor ?? null);
      } catch (e: any) {
        setError(getApiErrorCode(e) || e?.message || t('Failed to load albums'));
      } finally {
        setIsLoading(false);
      }
    },
    [cursor, query, t]
  );

  useEffect(() => {
    setAlbums([]);
    setCursor(null);
    loadPage(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  useEffect(() => {
    let cancelled = false;
    const missing = albums.filter((a) => a.coverMediaId && !covers[a.id]);
    if (missing.length === 0) return;
    (async () => {
      const results = await Promise.all(
        missing.map(async (a) => {
          try {
            const url = await apiClient.getPhotoThumbUrl(a.coverMediaId as number, 256);
            return url ? { id: a.id, url } : null;
          } catch {
            return null;
          }
        })
      );
      if (cancelled) return;
      const updates: Record<number, string> = {};
      for (const result of results) {
        if (result) updates[result.id] = result.url;
      }
      if (Object.keys(updates).length > 0) {
        setCovers((prev) => ({ ...prev, ...updates }));
      }
    })();
    return () => { cancelled = true; };
    // covers is intentionally excluded to avoid re-running as each URL resolves
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [albums]);

  const submitSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setQuery(search.trim());
  };

  const openCreate = () => {
    setEditTarget(null);
    setForm(defaultForm());
    setFormError(null);
    setShowForm(true);
  };

  const openEdit = (e: React.MouseEvent, album: AlbumSummary) => {
    e.preventDefault();
    e.stopPropagation();
    setEditTarget(album);
    setForm({ name: album.title, description: album.description || '', visibility: album.visibility || 'private' });
    setFormError(null);
    setShowForm(true);
  };

  const openDelete = (e: React.MouseEvent, album: AlbumSummary) => {
    e.preventDefault();
    e.stopPropagation();
    setDeleteTarget(album);
  };

  const submitForm = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) {
      setFormError(t('Album name is required'));
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      if (editTarget) {
        const res = await apiClient.updateAlbumItem(editTarget.id, {
          name: form.name.trim(),
          description: form.description.trim() || undefined,
          visibility: form.visibility,
        });
        setAlbums((prev) => prev.map((a) => (a.id === editTarget.id ? { ...a, ...res.album } : a)));
      } else {
        await apiClient.createAlbumItem({
          name: form.name.trim(),
          description: form.description.trim() || undefined,
          visibility: form.visibility,
        });
        setAlbums([]);
        setCursor(null);
        await loadPage(true);
      }
      setShowForm(false);
    } catch (e: any) {
      setFormError(e?.response?.data?.message || getApiErrorCode(e) || e?.message || t('Failed to save album'));
    } finally {
      setSubmitting(false);
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await apiClient.deleteAlbumItem(deleteTarget.id);
      setAlbums((prev) => prev.filter((a) => a.id !== deleteTarget.id));
      setDeleteTarget(null);
    } catch (e: any) {
      setError(e?.response?.data?.message || e?.message || t('Failed to delete album'));
      setDeleteTarget(null);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <Container fluid className="py-4" data-testid="albums-page">
      <Row className="mb-3 align-items-center">
        <Col>
          <h1 className="h3 mb-1">{t('Albums')}</h1>
          <p className="text-muted mb-0">{t('Your media albums')}</p>
        </Col>
        <Col xs="auto" className="d-flex gap-2">
          <Form className="d-flex" onSubmit={submitSearch}>
            <Form.Control
              type="search"
              placeholder={t('Search albums')}
              value={search}
              data-testid="albums-search"
              onChange={(e) => setSearch(e.target.value)}
            />
            <Button type="submit" variant="outline-primary" className="ms-2">
              {t('Search')}
            </Button>
          </Form>
          <Button variant="primary" onClick={openCreate} data-testid="albums-create">
            <i className="fa-solid fa-plus me-1" />{t('New Album')}
          </Button>
        </Col>
      </Row>

      {error && (
        <Alert variant="danger" dismissible onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {albums.length === 0 && !isLoading ? (
        <div className="text-center text-muted py-5" data-testid="albums-empty">
          {t('No albums found')}
        </div>
      ) : (
        <Row xs={2} sm={3} md={4} className="g-3">
          {albums.map((a) => (
            <Col key={a.id}>
              <Card
                className="h-100 position-relative"
                data-testid="album-card"
              >
                <Link
                  to={`/albums/${a.id}`}
                  style={{ textDecoration: 'none', color: 'inherit' }}
                >
                  <div
                    className="ratio ratio-4x3 bg-light d-flex align-items-center justify-content-center"
                    style={{ overflow: 'hidden' }}
                  >
                    {covers[a.id] ? (
                      <img
                        src={covers[a.id]}
                        alt={a.title}
                        style={{ objectFit: 'cover', width: '100%', height: '100%' }}
                      />
                    ) : (
                      <i className="fa-solid fa-book text-muted fs-1" />
                    )}
                  </div>
                  <Card.Body className="p-2">
                    <div className="fw-semibold text-truncate">{a.title}</div>
                    <Badge bg="secondary">{t('{{count}} items', { count: a.mediaCount })}</Badge>
                  </Card.Body>
                </Link>
                <div className="position-absolute top-0 end-0 p-1 d-flex gap-1">
                  <Button
                    size="sm"
                    variant="light"
                    className="opacity-75"
                    onClick={(e) => openEdit(e, a)}
                    data-testid="album-edit"
                    title={t('Edit')}
                  >
                    <i className="fa-solid fa-pen" />
                  </Button>
                  <Button
                    size="sm"
                    variant="light"
                    className="opacity-75"
                    onClick={(e) => openDelete(e, a)}
                    data-testid="album-delete"
                    title={t('Delete')}
                  >
                    <i className="fa-solid fa-trash" />
                  </Button>
                </div>
              </Card>
            </Col>
          ))}
        </Row>
      )}

      <div className="text-center mt-4">
        {isLoading ? (
          <Spinner animation="border" />
        ) : hasNext ? (
          <Button variant="outline-primary" onClick={() => loadPage(false)} data-testid="albums-load-more">
            {t('Load more')}
          </Button>
        ) : null}
      </div>

      {/* Create / Edit Modal */}
      <Modal show={showForm} onHide={() => setShowForm(false)} centered>
        <Form onSubmit={submitForm}>
          <Modal.Header closeButton>
            <Modal.Title>{editTarget ? t('Edit Album') : t('New Album')}</Modal.Title>
          </Modal.Header>
          <Modal.Body>
            {formError && <Alert variant="danger">{formError}</Alert>}
            <Form.Group className="mb-3">
              <Form.Label>{t('Album name')}</Form.Label>
              <Form.Control
                type="text"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                required
                autoFocus
                data-testid="album-form-name"
              />
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>{t('Description')}</Form.Label>
              <Form.Control
                as="textarea"
                rows={2}
                value={form.description}
                onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                data-testid="album-form-description"
              />
            </Form.Group>
            <Form.Group>
              <Form.Label>{t('Visibility')}</Form.Label>
              <Form.Select
                value={form.visibility}
                onChange={(e) => setForm((f) => ({ ...f, visibility: e.target.value }))}
                data-testid="album-form-visibility"
              >
                {VISIBILITY_OPTIONS.map((v) => (
                  <option key={v} value={v}>{t(`visibility_${v}`)}</option>
                ))}
              </Form.Select>
            </Form.Group>
          </Modal.Body>
          <Modal.Footer>
            <Button variant="secondary" onClick={() => setShowForm(false)}>
              {t('Cancel')}
            </Button>
            <Button type="submit" variant="primary" disabled={submitting} data-testid="album-form-submit">
              {submitting ? <Spinner size="sm" animation="border" /> : t('Save')}
            </Button>
          </Modal.Footer>
        </Form>
      </Modal>

      {/* Delete Confirm Modal */}
      <Modal show={!!deleteTarget} onHide={() => setDeleteTarget(null)} centered>
        <Modal.Header closeButton>
          <Modal.Title>{t('Delete Album')}</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {t('Delete album "{{name}}"?', { name: deleteTarget?.title })}
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setDeleteTarget(null)}>
            {t('Cancel')}
          </Button>
          <Button variant="danger" onClick={confirmDelete} disabled={deleting} data-testid="album-delete-confirm">
            {deleting ? <Spinner size="sm" animation="border" /> : t('Delete')}
          </Button>
        </Modal.Footer>
      </Modal>
    </Container>
  );
};

export default AlbumsPage;

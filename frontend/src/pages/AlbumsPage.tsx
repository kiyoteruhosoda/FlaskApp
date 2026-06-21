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
} from 'react-bootstrap';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../services/api';
import { AlbumSummary } from '../types/api';

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
        setError(e?.response?.data?.error || e?.message || t('Failed to load albums'));
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

  // 表紙サムネの署名URLを取得
  useEffect(() => {
    let cancelled = false;
    const missing = albums.filter((a) => a.coverMediaId && !covers[a.id]);
    if (missing.length === 0) return;
    (async () => {
      for (const a of missing) {
        try {
          const url = await apiClient.getPhotoThumbUrl(a.coverMediaId as number, 256);
          if (!cancelled && url) {
            setCovers((prev) => ({ ...prev, [a.id]: url }));
          }
        } catch {
          /* ignore */
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [albums, covers]);

  const submitSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setQuery(search.trim());
  };

  return (
    <Container fluid className="py-4" data-testid="albums-page">
      <Row className="mb-3 align-items-center">
        <Col>
          <h1 className="h3 mb-1">{t('Albums')}</h1>
          <p className="text-muted mb-0">{t('Your media albums')}</p>
        </Col>
        <Col xs="auto">
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
                className="h-100"
                role="button"
                href={`/photo-view/albums/${a.id}`}
                as="a"
                style={{ textDecoration: 'none', color: 'inherit' }}
                data-testid="album-card"
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
                    <i className="bi bi-book text-muted fs-1" />
                  )}
                </div>
                <Card.Body className="p-2">
                  <div className="fw-semibold text-truncate">{a.title}</div>
                  <Badge bg="secondary">{t('{{count}} items', { count: a.mediaCount })}</Badge>
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
          <Button variant="outline-primary" onClick={() => loadPage(false)} data-testid="albums-load-more">
            {t('Load more')}
          </Button>
        ) : null}
      </div>
    </Container>
  );
};

export default AlbumsPage;

import React, { useCallback, useEffect, useState } from 'react';
import {
  Container,
  Row,
  Col,
  Card,
  Form,
  Button,
  Spinner,
  Alert,
  Badge,
} from 'react-bootstrap';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../services/api';
import { MediaTag } from '../types/api';

const TagsPage: React.FC = () => {
  const { t } = useTranslation();

  const [tags, setTags] = useState<MediaTag[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');

  const loadTags = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiClient.getTags({ q: query || undefined, limit: 100 });
      setTags(data.items || []);
    } catch (e: any) {
      setError(e?.response?.data?.error || e?.message || t('Failed to load tags'));
    } finally {
      setIsLoading(false);
    }
  }, [query, t]);

  useEffect(() => {
    loadTags();
  }, [loadTags]);

  const submitSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setQuery(search.trim());
  };

  return (
    <Container fluid className="py-4" data-testid="tags-page">
      <Row className="mb-3 align-items-center">
        <Col>
          <h1 className="h3 mb-1">{t('Tags')}</h1>
          <p className="text-muted mb-0">{t('Registered media tags')}</p>
        </Col>
        <Col xs="auto">
          <Form className="d-flex" onSubmit={submitSearch}>
            <Form.Control
              type="search"
              placeholder={t('Search tags')}
              value={search}
              data-testid="tags-search"
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

      <Card>
        <Card.Body>
          {isLoading ? (
            <div className="text-center py-4">
              <Spinner animation="border" />
            </div>
          ) : tags.length === 0 ? (
            <div className="text-center text-muted py-4" data-testid="tags-empty">
              {t('No tags found')}
            </div>
          ) : (
            <div className="d-flex flex-wrap gap-2" data-testid="tags-list">
              {tags.map((tag) => (
                <Badge
                  key={tag.id}
                  bg="light"
                  text="dark"
                  className="border p-2"
                  data-testid="tag-item"
                >
                  <i className="bi bi-tag me-1" />
                  {tag.name}
                  {tag.attr && <span className="text-muted ms-1">({tag.attr})</span>}
                </Badge>
              ))}
            </div>
          )}
        </Card.Body>
      </Card>
    </Container>
  );
};

export default TagsPage;

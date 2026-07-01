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
  Modal,
} from 'react-bootstrap';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../services/api';
import { MediaTag } from '../types/api';

const TAG_ATTRS = ['person', 'place', 'event', 'scene', 'activity', 'thing', 'source', 'others'] as const;

const TagsPage: React.FC = () => {
  const { t } = useTranslation();

  const [tags, setTags] = useState<MediaTag[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');

  // create modal
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [newAttr, setNewAttr] = useState<string>(TAG_ATTRS[0]);
  const [createError, setCreateError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

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

  const openCreate = () => {
    setNewName('');
    setNewAttr(TAG_ATTRS[0]);
    setCreateError(null);
    setShowCreate(true);
  };

  const submitCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = newName.trim();
    if (!trimmed) {
      setCreateError(t('Tag name is required'));
      return;
    }
    setCreating(true);
    setCreateError(null);
    try {
      const res = await apiClient.createTag(trimmed, newAttr);
      if (res.created) {
        setTags((prev) => [...prev, res.tag].sort((a, b) => a.name.localeCompare(b.name)));
      }
      setShowCreate(false);
    } catch (e: any) {
      const status = (e as any)?.response?.status;
      if (status === 403) {
        setCreateError(t('You do not have permission to create tags'));
      } else {
        setCreateError(e?.response?.data?.message || e?.response?.data?.error || e?.message || t('Failed to create tag'));
      }
    } finally {
      setCreating(false);
    }
  };

  return (
    <Container fluid className="py-4" data-testid="tags-page">
      <Row className="mb-3 align-items-center">
        <Col>
          <h1 className="h3 mb-1">{t('Tags')}</h1>
          <p className="text-muted mb-0">{t('Registered media tags')}</p>
        </Col>
        <Col xs="auto" className="d-flex gap-2">
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
          <Button variant="primary" onClick={openCreate} data-testid="tags-create">
            <i className="fa-solid fa-plus me-1" />{t('New Tag')}
          </Button>
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
                  <i className="fa-solid fa-tag me-1" />
                  {tag.name}
                  {tag.attr && <span className="text-muted ms-1">({tag.attr})</span>}
                </Badge>
              ))}
            </div>
          )}
        </Card.Body>
      </Card>

      {/* Create Tag Modal */}
      <Modal show={showCreate} onHide={() => setShowCreate(false)} centered>
        <Form onSubmit={submitCreate}>
          <Modal.Header closeButton>
            <Modal.Title>{t('New Tag')}</Modal.Title>
          </Modal.Header>
          <Modal.Body>
            {createError && <Alert variant="danger">{createError}</Alert>}
            <Form.Group className="mb-3">
              <Form.Label>{t('Tag name')}</Form.Label>
              <Form.Control
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                required
                autoFocus
                data-testid="tag-form-name"
              />
            </Form.Group>
            <Form.Group>
              <Form.Label>{t('Attribute')}</Form.Label>
              <Form.Select
                value={newAttr}
                onChange={(e) => setNewAttr(e.target.value)}
                data-testid="tag-form-attr"
              >
                {TAG_ATTRS.map((a) => (
                  <option key={a} value={a}>{t(`tag_attr_${a}`)}</option>
                ))}
              </Form.Select>
            </Form.Group>
          </Modal.Body>
          <Modal.Footer>
            <Button variant="secondary" onClick={() => setShowCreate(false)}>{t('Cancel')}</Button>
            <Button type="submit" variant="primary" disabled={creating} data-testid="tag-form-submit">
              {creating ? <Spinner size="sm" animation="border" /> : t('Create')}
            </Button>
          </Modal.Footer>
        </Form>
      </Modal>
    </Container>
  );
};

export default TagsPage;

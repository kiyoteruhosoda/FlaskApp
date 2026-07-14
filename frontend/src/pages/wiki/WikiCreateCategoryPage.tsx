import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Container, Card, Form, Button, Spinner, Alert } from 'react-bootstrap';
import { wikiApi } from '../../services/wikiApi';
import { getApiErrorCode } from '../../services/apiErrors';

const WikiCreateCategoryPage: React.FC = () => {
  const navigate = useNavigate();

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [slug, setSlug] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const autoSlug = (t: string) =>
    t.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');

  const handleNameChange = (v: string) => {
    setName(v);
    if (!slug) setSlug(autoSlug(v));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const cat = await wikiApi.createCategory({
        name,
        description: description || undefined,
        slug: slug || undefined,
      });
      navigate(`/wiki/category/${cat.slug}`);
    } catch (err: any) {
      setError(getApiErrorCode(err) || err?.message || 'Failed to create category');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Container className="py-4" style={{ maxWidth: 640 }} data-testid="wiki-create-category-page">
      <div className="d-flex align-items-center mb-3">
        <Link to="/wiki/categories" className="btn btn-outline-secondary btn-sm me-3">
          <i className="fa-solid fa-arrow-left me-1" />Back
        </Link>
        <h1 className="h3 mb-0">New Category</h1>
      </div>

      {error && <Alert variant="danger" dismissible onClose={() => setError(null)}>{error}</Alert>}

      <Card>
        <Card.Body>
          <Form onSubmit={handleSubmit}>
            <Form.Group className="mb-3">
              <Form.Label>Name <span className="text-danger">*</span></Form.Label>
              <Form.Control
                type="text"
                value={name}
                onChange={(e) => handleNameChange(e.target.value)}
                required
                autoFocus
                placeholder="Category name"
              />
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Label>Description</Form.Label>
              <Form.Control
                as="textarea"
                rows={3}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Optional description"
              />
            </Form.Group>

            <Form.Group className="mb-4">
              <Form.Label>Slug</Form.Label>
              <Form.Control
                type="text"
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
                placeholder="url-friendly-slug"
              />
              <Form.Text className="text-muted">Leave blank to auto-generate from name.</Form.Text>
            </Form.Group>

            <div className="d-flex gap-2">
              <Button type="submit" variant="primary" disabled={submitting} className="flex-grow-1">
                {submitting ? <Spinner size="sm" animation="border" /> : 'Create Category'}
              </Button>
              <Link to="/wiki/categories" className="btn btn-secondary">Cancel</Link>
            </div>
          </Form>
        </Card.Body>
      </Card>
    </Container>
  );
};

export default WikiCreateCategoryPage;

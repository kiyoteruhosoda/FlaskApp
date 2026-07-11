import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Container, Card, Form, Button, Spinner, Alert, Row, Col, Tab, Tabs,
} from 'react-bootstrap';
import { wikiApi } from '../../services/wikiApi';
import { WikiCreateFormData } from '../../types/wiki';
import { getApiErrorCode } from '../../services/apiErrors';

const WikiCreatePage: React.FC = () => {
  const navigate = useNavigate();

  const [formData, setFormData] = useState<WikiCreateFormData | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [title, setTitle] = useState('');
  const [slug, setSlug] = useState('');
  const [content, setContent] = useState('');
  const [parentId, setParentId] = useState<string>('');
  const [categoryIds, setCategoryIds] = useState<number[]>([]);
  const [previewHtml, setPreviewHtml] = useState<string>('');
  const [previewing, setPreviewing] = useState(false);

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    wikiApi.getCreateForm()
      .then(setFormData)
      .catch((e) => setLoadError(getApiErrorCode(e) || e?.message || 'Failed to load form'));
  }, []);

  const autoSlug = (t: string) =>
    t.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');

  const handleTitleChange = (t: string) => {
    setTitle(t);
    if (!slug) setSlug(autoSlug(t));
  };

  const handlePreview = async () => {
    setPreviewing(true);
    try {
      const html = await wikiApi.previewMarkdown(content);
      setPreviewHtml(html);
    } catch {
      setPreviewHtml('<p class="text-danger">Preview failed.</p>');
    } finally {
      setPreviewing(false);
    }
  };

  const toggleCategory = (id: number) => {
    setCategoryIds((prev) =>
      prev.includes(id) ? prev.filter((c) => c !== id) : [...prev, id]
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setSubmitError(null);
    try {
      const page = await wikiApi.createPage({
        title,
        content,
        slug: slug || undefined,
        parent_id: parentId ? parseInt(parentId, 10) : null,
        category_ids: categoryIds,
      });
      navigate(`/wiki/page/${page.slug}`);
    } catch (err: any) {
      setSubmitError(getApiErrorCode(err) || err?.message || 'Failed to create page');
    } finally {
      setSubmitting(false);
    }
  };

  if (loadError) {
    return (
      <Container className="py-4">
        <Alert variant="danger">{loadError}</Alert>
        <Link to="/wiki" className="btn btn-secondary">Back to Wiki</Link>
      </Container>
    );
  }

  if (!formData) {
    return (
      <div className="d-flex justify-content-center py-5">
        <Spinner animation="border" />
      </div>
    );
  }

  return (
    <Container fluid className="py-4">
      <div className="d-flex align-items-center mb-3">
        <Link to="/wiki" className="btn btn-outline-secondary btn-sm me-3">
          <i className="fa-solid fa-arrow-left me-1" />Back
        </Link>
        <h1 className="h3 mb-0">New Wiki Page</h1>
      </div>

      {submitError && <Alert variant="danger" dismissible onClose={() => setSubmitError(null)}>{submitError}</Alert>}

      <Form onSubmit={handleSubmit}>
        <Row>
          <Col md={8}>
            <Card className="mb-3">
              <Card.Body>
                <Form.Group className="mb-3">
                  <Form.Label>Title <span className="text-danger">*</span></Form.Label>
                  <Form.Control
                    type="text"
                    value={title}
                    onChange={(e) => handleTitleChange(e.target.value)}
                    required
                    placeholder="Page title"
                  />
                </Form.Group>

                <Form.Group className="mb-3">
                  <Form.Label>Slug</Form.Label>
                  <Form.Control
                    type="text"
                    value={slug}
                    onChange={(e) => setSlug(e.target.value)}
                    placeholder="url-friendly-slug (auto-generated from title)"
                  />
                  <Form.Text className="text-muted">Leave blank to auto-generate from title.</Form.Text>
                </Form.Group>

                <Form.Group>
                  <Form.Label>Content (Markdown) <span className="text-danger">*</span></Form.Label>
                  <Tabs defaultActiveKey="write" className="mb-2">
                    <Tab eventKey="write" title="Write">
                      <Form.Control
                        as="textarea"
                        rows={16}
                        value={content}
                        onChange={(e) => setContent(e.target.value)}
                        placeholder="Write your page content in Markdown..."
                        required
                      />
                    </Tab>
                    <Tab
                      eventKey="preview"
                      title={previewing ? 'Loading…' : 'Preview'}
                      onEnter={handlePreview}
                    >
                      <div
                        className="border rounded p-3 wiki-content"
                        style={{ minHeight: 300 }}
                        dangerouslySetInnerHTML={{ __html: previewHtml || '<em class="text-muted">Nothing to preview yet.</em>' }}
                      />
                    </Tab>
                  </Tabs>
                </Form.Group>
              </Card.Body>
            </Card>
          </Col>

          <Col md={4}>
            <Card className="mb-3">
              <Card.Header><strong>Settings</strong></Card.Header>
              <Card.Body>
                <Form.Group className="mb-3">
                  <Form.Label>Parent Page</Form.Label>
                  <Form.Select value={parentId} onChange={(e) => setParentId(e.target.value)}>
                    <option value="">— None —</option>
                    {formData.pages.map((p) => (
                      <option key={p.id} value={p.id}>{p.title}</option>
                    ))}
                  </Form.Select>
                </Form.Group>

                {formData.categories.length > 0 && (
                  <Form.Group>
                    <Form.Label>Categories</Form.Label>
                    {formData.categories.map((cat) => (
                      <Form.Check
                        key={cat.id}
                        type="checkbox"
                        id={`cat-${cat.id}`}
                        label={cat.name}
                        checked={categoryIds.includes(cat.id)}
                        onChange={() => toggleCategory(cat.id)}
                      />
                    ))}
                  </Form.Group>
                )}
              </Card.Body>
            </Card>

            <div className="d-flex gap-2">
              <Button type="submit" variant="primary" disabled={submitting} className="flex-grow-1">
                {submitting ? <Spinner size="sm" animation="border" /> : 'Create Page'}
              </Button>
              <Link to="/wiki" className="btn btn-secondary">Cancel</Link>
            </div>
          </Col>
        </Row>
      </Form>
    </Container>
  );
};

export default WikiCreatePage;

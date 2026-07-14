import React, { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  Container, Card, Form, Button, Spinner, Alert, Row, Col, Tab, Tabs,
} from 'react-bootstrap';
import { wikiApi } from '../../services/wikiApi';
import { WikiEditFormData } from '../../types/wiki';
import { getApiErrorCode } from '../../services/apiErrors';

const WikiEditPage: React.FC = () => {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();

  const [formData, setFormData] = useState<WikiEditFormData | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [changeSummary, setChangeSummary] = useState('');
  const [categoryIds, setCategoryIds] = useState<number[]>([]);
  const [previewHtml, setPreviewHtml] = useState<string>('');
  const [previewing, setPreviewing] = useState(false);

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    if (!slug) return;
    wikiApi.getEditForm(slug)
      .then((data) => {
        setFormData(data);
        setTitle(data.page.title);
        setContent(data.page.content);
        setCategoryIds(data.page.id ? [] : []); // will be set below
        // Determine which categories are already assigned via form data
        // (the API returns all available categories; page's actual categories
        // are not directly in edit-form, so we'll keep current state as empty
        // unless we enrich it — for now users can re-select)
      })
      .catch((e) => {
        if (e?.response?.status === 403) {
          setLoadError('You do not have permission to edit this page.');
        } else if (e?.response?.status === 404) {
          setLoadError('Page not found.');
        } else {
          setLoadError(getApiErrorCode(e) || e?.message || 'Failed to load page');
        }
      });
  }, [slug]);

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
    if (!slug) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const page = await wikiApi.updatePage(slug, {
        title,
        content,
        change_summary: changeSummary || undefined,
        category_ids: categoryIds,
      });
      navigate(`/wiki/page/${page.slug}`);
    } catch (err: any) {
      if (err?.response?.status === 403) {
        setSubmitError('You do not have permission to edit this page.');
      } else {
        setSubmitError(getApiErrorCode(err) || err?.message || 'Failed to update page');
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (loadError) {
    return (
      <Container className="py-4">
        <Alert variant="danger">{loadError}</Alert>
        <Link to={slug ? `/wiki/page/${slug}` : '/wiki'} className="btn btn-secondary">Back</Link>
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
    <Container fluid className="py-4" data-testid="wiki-edit-page">
      <div className="d-flex align-items-center mb-3">
        <Link to={`/wiki/page/${slug}`} className="btn btn-outline-secondary btn-sm me-3">
          <i className="fa-solid fa-arrow-left me-1" />Back
        </Link>
        <h1 className="h3 mb-0">Edit: {formData.page.title}</h1>
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
                    onChange={(e) => setTitle(e.target.value)}
                    required
                  />
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
              <Card.Header><strong>Edit Settings</strong></Card.Header>
              <Card.Body>
                <Form.Group className="mb-3">
                  <Form.Label>Change Summary</Form.Label>
                  <Form.Control
                    type="text"
                    value={changeSummary}
                    onChange={(e) => setChangeSummary(e.target.value)}
                    placeholder="Brief description of changes"
                  />
                </Form.Group>

                {formData.categories.length > 0 && (
                  <Form.Group>
                    <Form.Label>Categories</Form.Label>
                    {formData.categories.map((cat) => (
                      <Form.Check
                        key={cat.id}
                        type="checkbox"
                        id={`edit-cat-${cat.id}`}
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
                {submitting ? <Spinner size="sm" animation="border" /> : 'Save Changes'}
              </Button>
              <Link to={`/wiki/page/${slug}`} className="btn btn-secondary">Cancel</Link>
            </div>
          </Col>
        </Row>
      </Form>
    </Container>
  );
};

export default WikiEditPage;

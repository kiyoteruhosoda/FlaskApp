import React, { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Container, Row, Col, Card, Badge, Spinner, Alert, Button, Modal } from 'react-bootstrap';
import { wikiApi } from '../../services/wikiApi';
import { WikiPageDetailData } from '../../types/wiki';
import { getApiErrorCode } from '../../services/apiErrors';

const WikiPageDetailPage: React.FC = () => {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();

  const [data, setData] = useState<WikiPageDetailData | null>(null);
  const [renderedHtml, setRenderedHtml] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    if (!slug) return;
    setLoading(true);
    setError(null);
    wikiApi.getPage(slug)
      .then(async (d) => {
        setData(d);
        const html = await wikiApi.previewMarkdown(d.page.content);
        setRenderedHtml(html);
      })
      .catch((e) => {
        if (e?.response?.status === 404) {
          setError('Page not found.');
        } else {
          setError(getApiErrorCode(e) || e?.message || 'Failed to load page');
        }
      })
      .finally(() => setLoading(false));
  }, [slug]);

  const handleDelete = async () => {
    if (!slug) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await wikiApi.deletePage(slug);
      setShowDeleteModal(false);
      navigate('/wiki');
    } catch (e: any) {
      setDeleteError(getApiErrorCode(e) || e?.message || 'Failed to delete page');
    } finally {
      setDeleting(false);
    }
  };

  if (loading) {
    return (
      <div className="d-flex justify-content-center py-5">
        <Spinner animation="border" />
      </div>
    );
  }

  if (error) {
    return (
      <Container className="py-4">
        <Alert variant="danger">{error}</Alert>
        <Link to="/wiki" className="btn btn-secondary">Back to Wiki</Link>
      </Container>
    );
  }

  const page = data!.page;

  return (
    <Container fluid className="py-4">
      <Row>
        <Col md={9}>
          {/* Breadcrumb */}
          {data!.page_hierarchy.length > 0 && (
            <nav aria-label="breadcrumb" className="mb-3">
              <ol className="breadcrumb">
                <li className="breadcrumb-item">
                  <Link to="/wiki">Wiki</Link>
                </li>
                {data!.page_hierarchy.map((item) => (
                  <li key={item.id} className="breadcrumb-item">
                    <Link to={`/wiki/page/${item.slug}`}>{item.title}</Link>
                  </li>
                ))}
                <li className="breadcrumb-item active">{page.title}</li>
              </ol>
            </nav>
          )}

          <div className="d-flex align-items-center justify-content-between mb-3">
            <h1 className="h2 mb-0">{page.title}</h1>
            <div className="d-flex gap-2">
              <Link to={`/wiki/history/${page.slug}`} className="btn btn-outline-secondary btn-sm">
                <i className="fa-solid fa-clock-rotate-left me-1" />History
              </Link>
              <Link to={`/wiki/edit/${page.slug}`} className="btn btn-outline-primary btn-sm">
                <i className="fa-solid fa-pen me-1" />Edit
              </Link>
              <Button variant="outline-danger" size="sm" onClick={() => setShowDeleteModal(true)}>
                <i className="fa-solid fa-trash me-1" />Delete
              </Button>
            </div>
          </div>

          {data!.categories.length > 0 && (
            <div className="mb-3 d-flex flex-wrap gap-1">
              {data!.categories.map((cat) => (
                <Link key={cat.id} to={`/wiki/category/${cat.slug}`} className="text-decoration-none">
                  <Badge bg="secondary">{cat.name}</Badge>
                </Link>
              ))}
            </div>
          )}

          <Card>
            <Card.Body>
              {renderedHtml ? (
                <div
                  className="wiki-content"
                  dangerouslySetInnerHTML={{ __html: renderedHtml }}
                />
              ) : (
                <pre className="mb-0" style={{ whiteSpace: 'pre-wrap' }}>{page.content}</pre>
              )}
            </Card.Body>
          </Card>

          <div className="mt-2 text-muted small">
            Last updated: {page.updated_at ? new Date(page.updated_at).toLocaleString() : 'Unknown'}
          </div>

          {data!.children.length > 0 && (
            <Card className="mt-4">
              <Card.Header><strong>Child Pages</strong></Card.Header>
              <Card.Body>
                <ul className="list-unstyled mb-0">
                  {data!.children.map((child: any) => (
                    <li key={child.id} className="mb-1">
                      <Link to={`/wiki/page/${child.slug}`} className="text-decoration-none">
                        {child.title}
                      </Link>
                    </li>
                  ))}
                </ul>
              </Card.Body>
            </Card>
          )}
        </Col>

        <Col md={3}>
          <Card>
            <Card.Header><strong>Page Info</strong></Card.Header>
            <Card.Body className="small">
              <div className="mb-2">
                <strong>Status:</strong>{' '}
                <Badge bg={page.is_published ? 'success' : 'secondary'}>
                  {page.is_published ? 'Published' : 'Draft'}
                </Badge>
              </div>
              <div className="mb-2">
                <strong>Created:</strong>{' '}
                {page.created_at ? new Date(page.created_at).toLocaleDateString() : 'Unknown'}
              </div>
              <div>
                <strong>Updated:</strong>{' '}
                {page.updated_at ? new Date(page.updated_at).toLocaleDateString() : 'Unknown'}
              </div>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* Delete Confirmation Modal */}
      <Modal show={showDeleteModal} onHide={() => setShowDeleteModal(false)} centered>
        <Modal.Header closeButton>
          <Modal.Title>Delete Page</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {deleteError && <Alert variant="danger">{deleteError}</Alert>}
          <p>Are you sure you want to delete <strong>{page.title}</strong>? This action cannot be undone.</p>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setShowDeleteModal(false)}>Cancel</Button>
          <Button variant="danger" onClick={handleDelete} disabled={deleting}>
            {deleting ? <Spinner size="sm" animation="border" /> : 'Delete'}
          </Button>
        </Modal.Footer>
      </Modal>
    </Container>
  );
};

export default WikiPageDetailPage;

import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Container, Row, Col, Card, Badge, Spinner, Alert } from 'react-bootstrap';
import { wikiApi } from '../../services/wikiApi';
import { WikiIndexData, WikiPageHierarchyItem } from '../../types/wiki';

function HierarchyTree({ items }: { items: WikiPageHierarchyItem[] }) {
  return (
    <ul className="list-unstyled mb-0">
      {items.map((item) => (
        <li key={item.id} className="mb-1">
          <Link to={`/wiki/page/${item.slug}`} className="text-decoration-none">
            {item.title}
          </Link>
          {item.children && item.children.length > 0 && (
            <div className="ms-3">
              <HierarchyTree items={item.children} />
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

const WikiIndexPage: React.FC = () => {
  const [data, setData] = useState<WikiIndexData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    wikiApi.getIndex()
      .then(setData)
      .catch((e) => setError(e?.response?.data?.error || e?.message || 'Failed to load wiki'))
      .finally(() => setLoading(false));
  }, []);

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
      </Container>
    );
  }

  return (
    <Container fluid className="py-4">
      <Row className="mb-3 align-items-center">
        <Col>
          <h1 className="h3 mb-0">Wiki</h1>
        </Col>
        <Col xs="auto" className="d-flex gap-2">
          <Link to="/wiki/search" className="btn btn-outline-secondary btn-sm">
            <i className="bi bi-search me-1" />Search
          </Link>
          <Link to="/wiki/create" className="btn btn-primary btn-sm">
            <i className="bi bi-plus-lg me-1" />New Page
          </Link>
          <Link to="/wiki/categories" className="btn btn-outline-secondary btn-sm">
            <i className="bi bi-tags me-1" />Categories
          </Link>
          <Link to="/wiki/admin" className="btn btn-outline-secondary btn-sm">
            <i className="bi bi-gear me-1" />Admin
          </Link>
        </Col>
      </Row>

      <Row>
        <Col md={8}>
          <Card className="mb-4">
            <Card.Header>
              <strong>Recent Pages</strong>
            </Card.Header>
            <Card.Body>
              {data?.recent_pages.length === 0 ? (
                <p className="text-muted mb-0">No pages yet.</p>
              ) : (
                <ul className="list-unstyled mb-0">
                  {data?.recent_pages.map((page) => (
                    <li key={page.id} className="mb-2 d-flex align-items-center justify-content-between">
                      <Link to={`/wiki/page/${page.slug}`} className="text-decoration-none fw-medium">
                        {page.title}
                      </Link>
                      <small className="text-muted ms-2">
                        {page.updated_at ? new Date(page.updated_at).toLocaleDateString() : ''}
                      </small>
                    </li>
                  ))}
                </ul>
              )}
            </Card.Body>
          </Card>

          {data?.page_hierarchy && data.page_hierarchy.length > 0 && (
            <Card>
              <Card.Header>
                <strong>Page Structure</strong>
              </Card.Header>
              <Card.Body>
                <HierarchyTree items={data.page_hierarchy} />
              </Card.Body>
            </Card>
          )}
        </Col>

        <Col md={4}>
          <Card>
            <Card.Header>
              <strong>Categories</strong>
            </Card.Header>
            <Card.Body>
              {data?.categories.length === 0 ? (
                <p className="text-muted mb-0">No categories yet.</p>
              ) : (
                <div className="d-flex flex-wrap gap-2">
                  {data?.categories.map((cat) => (
                    <Link
                      key={cat.id}
                      to={`/wiki/category/${cat.slug}`}
                      className="text-decoration-none"
                    >
                      <Badge bg="secondary">{cat.name}</Badge>
                    </Link>
                  ))}
                </div>
              )}
              <div className="mt-3">
                <Link to="/wiki/categories/create" className="btn btn-outline-primary btn-sm">
                  <i className="bi bi-plus me-1" />New Category
                </Link>
              </div>
            </Card.Body>
          </Card>
        </Col>
      </Row>
    </Container>
  );
};

export default WikiIndexPage;

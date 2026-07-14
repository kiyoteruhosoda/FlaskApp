import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Container, Row, Col, Card, Spinner, Alert } from 'react-bootstrap';
import { wikiApi } from '../../services/wikiApi';
import { WikiAdminData } from '../../types/wiki';
import { getApiErrorCode } from '../../services/apiErrors';

const WikiAdminPage: React.FC = () => {
  const [data, setData] = useState<WikiAdminData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    wikiApi.getAdminData()
      .then(setData)
      .catch((e) => {
        if (e?.response?.status === 403) {
          setError('You do not have permission to access the admin dashboard.');
        } else {
          setError(getApiErrorCode(e) || e?.message || 'Failed to load admin data');
        }
      })
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
        <Link to="/wiki" className="btn btn-secondary">Back to Wiki</Link>
      </Container>
    );
  }

  const { total_pages, total_categories, recent_pages } = data!;

  return (
    <Container fluid className="py-4" data-testid="wiki-admin-page">
      <div className="d-flex align-items-center mb-4">
        <Link to="/wiki" className="btn btn-outline-secondary btn-sm me-3">
          <i className="fa-solid fa-arrow-left me-1" />Wiki
        </Link>
        <h1 className="h3 mb-0">Wiki Admin</h1>
      </div>

      <Row className="g-3 mb-4">
        <Col sm={6} md={3}>
          <Card className="text-center">
            <Card.Body>
              <div className="display-4 fw-bold text-primary">{total_pages}</div>
              <div className="text-muted">Total Pages</div>
            </Card.Body>
          </Card>
        </Col>
        <Col sm={6} md={3}>
          <Card className="text-center">
            <Card.Body>
              <div className="display-4 fw-bold text-success">{total_categories}</div>
              <div className="text-muted">Total Categories</div>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      <Row className="g-3">
        <Col md={8}>
          <Card>
            <Card.Header><strong>Recent Pages</strong></Card.Header>
            <Card.Body>
              {recent_pages.length === 0 ? (
                <p className="text-muted mb-0">No pages yet.</p>
              ) : (
                <ul className="list-unstyled mb-0">
                  {recent_pages.map((page) => (
                    <li key={page.id} className="mb-2 d-flex align-items-center justify-content-between">
                      <Link to={`/wiki/page/${page.slug}`} className="text-decoration-none">
                        {page.title}
                      </Link>
                      <div className="d-flex gap-2 ms-2">
                        <Link to={`/wiki/edit/${page.slug}`} className="btn btn-outline-secondary btn-sm">
                          <i className="fa-solid fa-pen" />
                        </Link>
                        <Link to={`/wiki/history/${page.slug}`} className="btn btn-outline-secondary btn-sm">
                          <i className="fa-solid fa-clock-rotate-left" />
                        </Link>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Card.Body>
          </Card>
        </Col>

        <Col md={4}>
          <Card>
            <Card.Header><strong>Quick Actions</strong></Card.Header>
            <Card.Body className="d-flex flex-column gap-2">
              <Link to="/wiki/create" className="btn btn-primary">
                <i className="fa-solid fa-plus me-2" />New Page
              </Link>
              <Link to="/wiki/categories/create" className="btn btn-outline-primary">
                <i className="fa-solid fa-tag me-2" />New Category
              </Link>
              <Link to="/wiki/categories" className="btn btn-outline-secondary">
                <i className="fa-solid fa-tags me-2" />Manage Categories
              </Link>
            </Card.Body>
          </Card>
        </Col>
      </Row>
    </Container>
  );
};

export default WikiAdminPage;

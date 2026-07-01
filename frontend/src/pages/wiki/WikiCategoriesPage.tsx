import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Container, Row, Col, Card, Badge, Spinner, Alert } from 'react-bootstrap';
import { wikiApi } from '../../services/wikiApi';
import { WikiCategory } from '../../types/wiki';

const WikiCategoriesPage: React.FC = () => {
  const [categories, setCategories] = useState<WikiCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    wikiApi.getCategories()
      .then(setCategories)
      .catch((e) => setError(e?.response?.data?.error || e?.message || 'Failed to load categories'))
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
          <div className="d-flex align-items-center gap-3">
            <Link to="/wiki" className="btn btn-outline-secondary btn-sm">
              <i className="fa-solid fa-arrow-left me-1" />Wiki
            </Link>
            <h1 className="h3 mb-0">Categories</h1>
          </div>
        </Col>
        <Col xs="auto">
          <Link to="/wiki/categories/create" className="btn btn-primary btn-sm">
            <i className="fa-solid fa-plus me-1" />New Category
          </Link>
        </Col>
      </Row>

      {categories.length === 0 ? (
        <Card>
          <Card.Body className="text-center text-muted py-5">
            <i className="fa-solid fa-tags fs-2 d-block mb-2" />
            <p className="mb-2">No categories yet.</p>
            <Link to="/wiki/categories/create" className="btn btn-primary btn-sm">Create the first category</Link>
          </Card.Body>
        </Card>
      ) : (
        <Row xs={1} sm={2} md={3} lg={4} className="g-3">
          {categories.map((cat) => (
            <Col key={cat.id}>
              <Card className="h-100">
                <Card.Body>
                  <Link to={`/wiki/category/${cat.slug}`} className="text-decoration-none">
                    <h5 className="card-title">{cat.name}</h5>
                  </Link>
                  {cat.description && (
                    <p className="card-text text-muted small">{cat.description}</p>
                  )}
                  <Badge bg="light" text="dark" className="border">
                    {cat.page_count ?? 0} page{cat.page_count !== 1 ? 's' : ''}
                  </Badge>
                </Card.Body>
              </Card>
            </Col>
          ))}
        </Row>
      )}
    </Container>
  );
};

export default WikiCategoriesPage;

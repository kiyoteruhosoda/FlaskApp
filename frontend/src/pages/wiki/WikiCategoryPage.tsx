import React, { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Container, Card, Spinner, Alert } from 'react-bootstrap';
import { wikiApi } from '../../services/wikiApi';
import { WikiCategoryDetailData } from '../../types/wiki';

const WikiCategoryPage: React.FC = () => {
  const { slug } = useParams<{ slug: string }>();
  const [data, setData] = useState<WikiCategoryDetailData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!slug) return;
    wikiApi.getCategory(slug)
      .then(setData)
      .catch((e) => {
        if (e?.response?.status === 404) {
          setError('Category not found.');
        } else {
          setError(e?.response?.data?.error || e?.message || 'Failed to load category');
        }
      })
      .finally(() => setLoading(false));
  }, [slug]);

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
        <Link to="/wiki/categories" className="btn btn-secondary">Back to Categories</Link>
      </Container>
    );
  }

  const { category, pages } = data!;

  return (
    <Container fluid className="py-4">
      <div className="d-flex align-items-center mb-3">
        <Link to="/wiki/categories" className="btn btn-outline-secondary btn-sm me-3">
          <i className="bi bi-arrow-left me-1" />Categories
        </Link>
        <h1 className="h3 mb-0">{category.name}</h1>
      </div>

      {category.description && (
        <p className="text-muted mb-4">{category.description}</p>
      )}

      <Card>
        <Card.Header>
          <strong>Pages in this category</strong>
          <span className="text-muted ms-2">({pages.length})</span>
        </Card.Header>
        <Card.Body>
          {pages.length === 0 ? (
            <p className="text-muted mb-0">No pages in this category.</p>
          ) : (
            <ul className="list-unstyled mb-0">
              {pages.map((page) => (
                <li key={page.id} className="mb-2 d-flex align-items-center justify-content-between">
                  <Link to={`/wiki/page/${page.slug}`} className="text-decoration-none fw-medium">
                    {page.title}
                  </Link>
                  <small className="text-muted">
                    {page.updated_at ? new Date(page.updated_at).toLocaleDateString() : ''}
                  </small>
                </li>
              ))}
            </ul>
          )}
        </Card.Body>
      </Card>
    </Container>
  );
};

export default WikiCategoryPage;

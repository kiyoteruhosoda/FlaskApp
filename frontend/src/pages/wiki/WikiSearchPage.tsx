import React, { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Container, Card, Form, Button, Spinner, Alert, InputGroup } from 'react-bootstrap';
import { wikiApi } from '../../services/wikiApi';
import { WikiPage } from '../../types/wiki';
import { getApiErrorCode } from '../../services/apiErrors';

const WikiSearchPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialQuery = searchParams.get('q') || '';

  const [query, setQuery] = useState(initialQuery);
  const [submittedQuery, setSubmittedQuery] = useState(initialQuery);
  const [results, setResults] = useState<WikiPage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);

  useEffect(() => {
    if (!submittedQuery) return;
    setLoading(true);
    setError(null);
    wikiApi.search(submittedQuery)
      .then((data) => {
        setResults(data.pages);
        setSearched(true);
      })
      .catch((e) => setError(getApiErrorCode(e) || e?.message || 'Search failed'))
      .finally(() => setLoading(false));
  }, [submittedQuery]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const q = query.trim();
    setSearchParams(q ? { q } : {});
    setSubmittedQuery(q);
  };

  return (
    <Container fluid className="py-4">
      <div className="d-flex align-items-center mb-3">
        <Link to="/wiki" className="btn btn-outline-secondary btn-sm me-3">
          <i className="fa-solid fa-arrow-left me-1" />Wiki
        </Link>
        <h1 className="h3 mb-0">Search Wiki</h1>
      </div>

      <Card className="mb-4">
        <Card.Body>
          <Form onSubmit={handleSearch}>
            <InputGroup>
              <Form.Control
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search pages by title or content…"
                autoFocus
              />
              <Button type="submit" variant="primary">
                <i className="fa-solid fa-magnifying-glass me-1" />Search
              </Button>
            </InputGroup>
          </Form>
        </Card.Body>
      </Card>

      {loading && (
        <div className="d-flex justify-content-center py-4">
          <Spinner animation="border" />
        </div>
      )}

      {error && <Alert variant="danger">{error}</Alert>}

      {!loading && searched && (
        <>
          <p className="text-muted mb-3">
            {results.length === 0
              ? `No results for "${submittedQuery}".`
              : `${results.length} result${results.length !== 1 ? 's' : ''} for "${submittedQuery}"`}
          </p>
          {results.length > 0 && (
            <div className="d-flex flex-column gap-3">
              {results.map((page) => (
                <Card key={page.id}>
                  <Card.Body>
                    <Link to={`/wiki/page/${page.slug}`} className="h5 text-decoration-none d-block mb-1">
                      {page.title}
                    </Link>
                    <small className="text-muted">
                      /wiki/page/{page.slug} &nbsp;·&nbsp;
                      Updated: {page.updated_at ? new Date(page.updated_at).toLocaleDateString() : '—'}
                    </small>
                  </Card.Body>
                </Card>
              ))}
            </div>
          )}
        </>
      )}
    </Container>
  );
};

export default WikiSearchPage;

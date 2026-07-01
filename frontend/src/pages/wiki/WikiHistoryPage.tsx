import React, { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Container, Card, Badge, Spinner, Alert, Table } from 'react-bootstrap';
import { wikiApi } from '../../services/wikiApi';
import { WikiPageHistoryData } from '../../types/wiki';

const WikiHistoryPage: React.FC = () => {
  const { slug } = useParams<{ slug: string }>();
  const [data, setData] = useState<WikiPageHistoryData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!slug) return;
    wikiApi.getPageHistory(slug)
      .then(setData)
      .catch((e) => {
        if (e?.response?.status === 404) {
          setError('Page not found.');
        } else {
          setError(e?.response?.data?.error || e?.message || 'Failed to load history');
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
        <Link to="/wiki" className="btn btn-secondary">Back to Wiki</Link>
      </Container>
    );
  }

  const { page, revisions } = data!;

  return (
    <Container fluid className="py-4">
      <div className="d-flex align-items-center mb-3">
        <Link to={`/wiki/page/${page.slug}`} className="btn btn-outline-secondary btn-sm me-3">
          <i className="fa-solid fa-arrow-left me-1" />Back to Page
        </Link>
        <h1 className="h3 mb-0">History: {page.title}</h1>
      </div>

      <Card>
        <Card.Header>
          <strong>Revision History</strong>
          <span className="text-muted ms-2">({revisions.length} revision{revisions.length !== 1 ? 's' : ''})</span>
        </Card.Header>
        <Card.Body className="p-0">
          {revisions.length === 0 ? (
            <p className="text-muted p-3 mb-0">No revision history available.</p>
          ) : (
            <Table hover responsive className="mb-0">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Title</th>
                  <th>Change Summary</th>
                  <th>Date</th>
                </tr>
              </thead>
              <tbody>
                {revisions.map((rev, idx) => (
                  <tr key={rev.id}>
                    <td>
                      <Badge bg={idx === 0 ? 'primary' : 'secondary'}>
                        v{rev.revision_number}
                      </Badge>
                    </td>
                    <td>{rev.title}</td>
                    <td className="text-muted">
                      {rev.change_summary || <em className="text-muted">No summary</em>}
                    </td>
                    <td className="text-nowrap">
                      {rev.created_at ? new Date(rev.created_at).toLocaleString() : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card.Body>
      </Card>
    </Container>
  );
};

export default WikiHistoryPage;

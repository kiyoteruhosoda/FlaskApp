import React, { useEffect, useState } from 'react';
import { Container, Row, Col, Card, Spinner, Alert, Badge } from 'react-bootstrap';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../services/api';
import { DashboardStats } from '../types/api';

const StatCard: React.FC<{ title: string; value: number | string; icon: string; variant?: string }> = ({
  title, value, icon, variant = 'primary',
}) => (
  <Card className="h-100">
    <Card.Body className="d-flex align-items-center gap-3">
      <div className={`text-${variant} fs-2`}>
        <i className={`bi ${icon}`} />
      </div>
      <div>
        <div className="fs-4 fw-bold">{value}</div>
        <div className="text-muted small">{title}</div>
      </div>
    </Card.Body>
  </Card>
);

const AdminDashboardPage: React.FC = () => {
  const { t } = useTranslation();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiClient.getAdminDashboard()
      .then((res) => setStats(res.stats))
      .catch((e) => {
        const status = e?.response?.status;
        setError(status === 403 ? t('You do not have permission to view this page') : t('Failed to load dashboard'));
      })
      .finally(() => setLoading(false));
  }, [t]);

  const jobStatusVariant = (status: string) => {
    if (status === 'success') return 'success';
    if (status === 'failed') return 'danger';
    if (status === 'running') return 'primary';
    return 'secondary';
  };

  return (
    <Container fluid className="py-4" data-testid="admin-dashboard-page">
      <h1 className="h3 mb-1">{t('System Overview')}</h1>
      <p className="text-muted mb-4">{t('Application statistics and recent activity')}</p>

      {error && <Alert variant="danger">{error}</Alert>}

      {loading ? (
        <div className="text-center py-5"><Spinner animation="border" /></div>
      ) : stats && (
        <>
          <Row className="g-3 mb-4">
            <Col sm={6} xl={3}>
              <StatCard title={t('Total Users')} value={stats.users.total} icon="bi-people" />
            </Col>
            <Col sm={6} xl={3}>
              <StatCard title={t('Active Users')} value={stats.users.active} icon="bi-person-check" variant="success" />
            </Col>
            <Col sm={6} xl={3}>
              <StatCard title={t('Roles')} value={stats.roles} icon="bi-shield" variant="info" />
            </Col>
            <Col sm={6} xl={3}>
              <StatCard title={t('Groups')} value={stats.groups} icon="bi-diagram-3" variant="warning" />
            </Col>
            {stats.media && (
              <>
                <Col sm={6} xl={3}>
                  <StatCard title={t('Total Media')} value={stats.media.total} icon="bi-images" />
                </Col>
                <Col sm={6} xl={3}>
                  <StatCard title={t('Photos')} value={stats.media.photos} icon="bi-image" variant="success" />
                </Col>
                <Col sm={6} xl={3}>
                  <StatCard title={t('Videos')} value={stats.media.videos} icon="bi-camera-video" variant="info" />
                </Col>
              </>
            )}
            {stats.albums !== undefined && (
              <Col sm={6} xl={3}>
                <StatCard title={t('Albums')} value={stats.albums} icon="bi-collection" variant="warning" />
              </Col>
            )}
          </Row>

          <Card>
            <Card.Header className="fw-semibold">{t('Recent Sync Jobs')}</Card.Header>
            {stats.recentJobs.length === 0 ? (
              <Card.Body className="text-muted">{t('No jobs found')}</Card.Body>
            ) : (
              <div className="table-responsive">
                <table className="table table-hover mb-0">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>{t('Target')}</th>
                      <th>{t('Status')}</th>
                      <th>{t('Started')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stats.recentJobs.map((j) => (
                      <tr key={j.id}>
                        <td>{j.id}</td>
                        <td>{j.target}</td>
                        <td><Badge bg={jobStatusVariant(j.status)}>{j.status}</Badge></td>
                        <td className="text-muted small">{j.startedAt ? new Date(j.startedAt).toLocaleString() : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}
    </Container>
  );
};

export default AdminDashboardPage;

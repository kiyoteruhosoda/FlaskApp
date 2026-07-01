import React, { useCallback, useEffect, useState } from 'react';
import {
  Container, Row, Col, Table, Button, Form, Spinner, Alert, Badge, Modal,
} from 'react-bootstrap';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../services/api';
import { AdminServiceAccount } from '../types/api';

const COMMON_SCOPES = ['media:view', 'media:write', 'album:view', 'album:write', 'sync:run', 'user:manage', 'admin:system-settings'];

const ServiceAccountsPage: React.FC = () => {
  const { t } = useTranslation();
  const [accounts, setAccounts] = useState<AdminServiceAccount[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');

  const [showForm, setShowForm] = useState(false);
  const [editTarget, setEditTarget] = useState<AdminServiceAccount | null>(null);
  const [form, setForm] = useState({ name: '', description: '', scopes: [] as string[], isActive: true });
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [deleteTarget, setDeleteTarget] = useState<AdminServiceAccount | null>(null);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.getAdminServiceAccounts({ q: query || undefined });
      setAccounts(res.serviceAccounts);
    } catch (e: any) {
      setError(e?.response?.status === 403 ? t('You do not have permission to manage service accounts') : t('Failed to load service accounts'));
    } finally {
      setLoading(false);
    }
  }, [query, t]);

  useEffect(() => { load(); }, [load]);

  const submitSearch = (e: React.FormEvent) => { e.preventDefault(); setQuery(search.trim()); };

  const openCreate = () => {
    setEditTarget(null);
    setForm({ name: '', description: '', scopes: [], isActive: true });
    setFormError(null);
    setShowForm(true);
  };

  const openEdit = (sa: AdminServiceAccount) => {
    setEditTarget(sa);
    setForm({ name: sa.name, description: sa.description || '', scopes: sa.scopes || [], isActive: sa.isActive });
    setFormError(null);
    setShowForm(true);
  };

  const toggleScope = (scope: string) => {
    setForm((f) => ({
      ...f,
      scopes: f.scopes.includes(scope) ? f.scopes.filter((s) => s !== scope) : [...f.scopes, scope],
    }));
  };

  const submitForm = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) { setFormError(t('Service account name is required')); return; }
    setSubmitting(true);
    setFormError(null);
    try {
      if (editTarget) {
        const res = await apiClient.updateAdminServiceAccount(editTarget.id, {
          name: form.name.trim(),
          description: form.description.trim() || undefined,
          scopes: form.scopes,
          isActive: form.isActive,
        });
        setAccounts((prev) => prev.map((a) => a.id === editTarget.id ? res.serviceAccount : a));
      } else {
        const res = await apiClient.createAdminServiceAccount({
          name: form.name.trim(),
          description: form.description.trim() || undefined,
          scopes: form.scopes,
          isActive: form.isActive,
        });
        setAccounts((prev) => [...prev, res.serviceAccount]);
      }
      setShowForm(false);
    } catch (e: any) {
      const code = e?.response?.data?.error;
      setFormError(code === 'name_exists' ? t('Service account name already in use') : t('Failed to save service account'));
    } finally {
      setSubmitting(false);
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await apiClient.deleteAdminServiceAccount(deleteTarget.id);
      setAccounts((prev) => prev.filter((a) => a.id !== deleteTarget.id));
      setDeleteTarget(null);
    } catch (e: any) {
      setError(e?.response?.data?.message || t('Failed to delete service account'));
      setDeleteTarget(null);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <Container fluid className="py-4" data-testid="service-accounts-page">
      <Row className="mb-3 align-items-center">
        <Col>
          <h1 className="h3 mb-1">{t('Service Accounts')}</h1>
          <p className="text-muted mb-0">{t('Manage API service accounts and their scopes')}</p>
        </Col>
        <Col xs="auto" className="d-flex gap-2">
          <Form className="d-flex" onSubmit={submitSearch}>
            <Form.Control
              type="search"
              placeholder={t('Search service accounts')}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              data-testid="sa-search"
            />
            <Button type="submit" variant="outline-primary" className="ms-2">{t('Search')}</Button>
          </Form>
          <Button variant="primary" onClick={openCreate} data-testid="sa-create">
            <i className="fa-solid fa-plus me-1" />{t('New Service Account')}
          </Button>
        </Col>
      </Row>

      {error && <Alert variant="danger" dismissible onClose={() => setError(null)}>{error}</Alert>}

      {loading ? (
        <div className="text-center py-5"><Spinner animation="border" /></div>
      ) : accounts.length === 0 ? (
        <div className="text-center text-muted py-5" data-testid="sa-empty">{t('No service accounts found')}</div>
      ) : (
        <Table hover className="align-middle" data-testid="sa-table">
          <thead>
            <tr>
              <th>{t('Name')}</th>
              <th>{t('Description')}</th>
              <th>{t('Scopes')}</th>
              <th>{t('Status')}</th>
              <th>{t('Actions')}</th>
            </tr>
          </thead>
          <tbody>
            {accounts.map((a) => (
              <tr key={a.id} data-testid="sa-row">
                <td className="fw-semibold">{a.name}</td>
                <td className="text-muted">{a.description || '—'}</td>
                <td>
                  <div className="d-flex flex-wrap gap-1">
                    {(a.scopes || []).slice(0, 3).map((s) => (
                      <Badge key={s} bg="light" text="dark" className="border font-monospace">{s}</Badge>
                    ))}
                    {(a.scopes || []).length > 3 && (
                      <Badge bg="secondary">+{(a.scopes || []).length - 3}</Badge>
                    )}
                    {(a.scopes || []).length === 0 && <span className="text-muted small">—</span>}
                  </div>
                </td>
                <td>
                  <Badge bg={a.isActive ? 'success' : 'secondary'}>
                    {a.isActive ? t('Active') : t('Inactive')}
                  </Badge>
                </td>
                <td>
                  <div className="d-flex gap-1">
                    <Button size="sm" variant="outline-secondary" onClick={() => openEdit(a)} data-testid="sa-edit">
                      <i className="fa-solid fa-pen" />
                    </Button>
                    <Button size="sm" variant="outline-danger" onClick={() => setDeleteTarget(a)} data-testid="sa-delete">
                      <i className="fa-solid fa-trash" />
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}

      <Modal show={showForm} onHide={() => setShowForm(false)} centered>
        <Form onSubmit={submitForm}>
          <Modal.Header closeButton>
            <Modal.Title>{editTarget ? t('Edit Service Account') : t('New Service Account')}</Modal.Title>
          </Modal.Header>
          <Modal.Body>
            {formError && <Alert variant="danger">{formError}</Alert>}
            <Form.Group className="mb-3">
              <Form.Label>{t('Name')}</Form.Label>
              <Form.Control
                type="text"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                autoFocus
                required
                data-testid="sa-form-name"
              />
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>{t('Description')}</Form.Label>
              <Form.Control
                type="text"
                value={form.description}
                onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                placeholder={t('Optional description')}
                data-testid="sa-form-description"
              />
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>{t('Scopes')}</Form.Label>
              <div className="border rounded p-2">
                {COMMON_SCOPES.map((scope) => (
                  <Form.Check
                    key={scope}
                    type="checkbox"
                    id={`scope-${scope}`}
                    label={<code>{scope}</code>}
                    checked={form.scopes.includes(scope)}
                    onChange={() => toggleScope(scope)}
                  />
                ))}
              </div>
            </Form.Group>
            <Form.Check
              type="switch"
              id="sa-active-switch"
              label={t('Active')}
              checked={form.isActive}
              onChange={(e) => setForm((f) => ({ ...f, isActive: e.target.checked }))}
              data-testid="sa-form-active"
            />
          </Modal.Body>
          <Modal.Footer>
            <Button variant="secondary" onClick={() => setShowForm(false)}>{t('Cancel')}</Button>
            <Button type="submit" variant="primary" disabled={submitting} data-testid="sa-form-submit">
              {submitting ? <Spinner size="sm" animation="border" /> : t('Save')}
            </Button>
          </Modal.Footer>
        </Form>
      </Modal>

      <Modal show={!!deleteTarget} onHide={() => setDeleteTarget(null)} centered>
        <Modal.Header closeButton><Modal.Title>{t('Delete Service Account')}</Modal.Title></Modal.Header>
        <Modal.Body>{t('Delete service account "{{name}}"?', { name: deleteTarget?.name })}</Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setDeleteTarget(null)}>{t('Cancel')}</Button>
          <Button variant="danger" onClick={confirmDelete} disabled={deleting} data-testid="sa-delete-confirm">
            {deleting ? <Spinner size="sm" animation="border" /> : t('Delete')}
          </Button>
        </Modal.Footer>
      </Modal>
    </Container>
  );
};

export default ServiceAccountsPage;

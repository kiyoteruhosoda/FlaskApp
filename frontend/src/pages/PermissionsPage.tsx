import React, { useCallback, useEffect, useState } from 'react';
import {
  Container, Row, Col, Table, Button, Form, Spinner, Alert, Modal,
} from 'react-bootstrap';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../services/api';
import { AdminPermission } from '../types/api';

const PermissionsPage: React.FC = () => {
  const { t } = useTranslation();
  const [permissions, setPermissions] = useState<AdminPermission[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');

  const [showForm, setShowForm] = useState(false);
  const [editTarget, setEditTarget] = useState<AdminPermission | null>(null);
  const [form, setForm] = useState({ code: '', detail: '' });
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [deleteTarget, setDeleteTarget] = useState<AdminPermission | null>(null);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.getAdminPermissions({ q: query || undefined });
      setPermissions(res.permissions);
    } catch (e: any) {
      setError(e?.response?.status === 403 ? t('You do not have permission to manage permissions') : t('Failed to load permissions'));
    } finally {
      setLoading(false);
    }
  }, [query, t]);

  useEffect(() => { load(); }, [load]);

  const submitSearch = (e: React.FormEvent) => { e.preventDefault(); setQuery(search.trim()); };

  const openCreate = () => {
    setEditTarget(null);
    setForm({ code: '', detail: '' });
    setFormError(null);
    setShowForm(true);
  };

  const openEdit = (perm: AdminPermission) => {
    setEditTarget(perm);
    setForm({ code: perm.code, detail: perm.detail || '' });
    setFormError(null);
    setShowForm(true);
  };

  const submitForm = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.code.trim()) { setFormError(t('Permission code is required')); return; }
    setSubmitting(true);
    setFormError(null);
    try {
      if (editTarget) {
        const res = await apiClient.updateAdminPermission(editTarget.id, {
          code: form.code.trim(), detail: form.detail.trim() || undefined,
        });
        setPermissions((prev) => prev.map((p) => p.id === editTarget.id ? res.permission : p));
      } else {
        const res = await apiClient.createAdminPermission({ code: form.code.trim(), detail: form.detail.trim() || undefined });
        setPermissions((prev) => [...prev, res.permission]);
      }
      setShowForm(false);
    } catch (e: any) {
      const code = e?.response?.data?.error;
      setFormError(code === 'code_exists' ? t('Permission code already in use') : t('Failed to save permission'));
    } finally {
      setSubmitting(false);
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await apiClient.deleteAdminPermission(deleteTarget.id);
      setPermissions((prev) => prev.filter((p) => p.id !== deleteTarget.id));
      setDeleteTarget(null);
    } catch (e: any) {
      setError(e?.response?.data?.message || t('Failed to delete permission'));
      setDeleteTarget(null);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <Container fluid className="py-4" data-testid="permissions-page">
      <Row className="mb-3 align-items-center">
        <Col>
          <h1 className="h3 mb-1">{t('Permission Management')}</h1>
          <p className="text-muted mb-0">{t('Manage system permission codes')}</p>
        </Col>
        <Col xs="auto" className="d-flex gap-2">
          <Form className="d-flex" onSubmit={submitSearch}>
            <Form.Control
              type="search"
              placeholder={t('Search permissions')}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              data-testid="permissions-search"
            />
            <Button type="submit" variant="outline-primary" className="ms-2">{t('Search')}</Button>
          </Form>
          <Button variant="primary" onClick={openCreate} data-testid="permissions-create">
            <i className="fa-solid fa-plus me-1" />{t('New Permission')}
          </Button>
        </Col>
      </Row>

      {error && <Alert variant="danger" dismissible onClose={() => setError(null)}>{error}</Alert>}

      {loading ? (
        <div className="text-center py-5"><Spinner animation="border" /></div>
      ) : permissions.length === 0 ? (
        <div className="text-center text-muted py-5" data-testid="permissions-empty">{t('No permissions found')}</div>
      ) : (
        <Table hover className="align-middle" data-testid="permissions-table">
          <thead>
            <tr>
              <th>{t('Code')}</th>
              <th>{t('Detail')}</th>
              <th>{t('Roles')}</th>
              <th>{t('Actions')}</th>
            </tr>
          </thead>
          <tbody>
            {permissions.map((p) => (
              <tr key={p.id} data-testid="permission-row">
                <td><code>{p.code}</code></td>
                <td className="text-muted">{p.detail || '—'}</td>
                <td>{p.roleCount}</td>
                <td>
                  <div className="d-flex gap-1">
                    <Button size="sm" variant="outline-secondary" onClick={() => openEdit(p)} data-testid="permission-edit">
                      <i className="fa-solid fa-pen" />
                    </Button>
                    <Button size="sm" variant="outline-danger" onClick={() => setDeleteTarget(p)} data-testid="permission-delete">
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
            <Modal.Title>{editTarget ? t('Edit Permission') : t('New Permission')}</Modal.Title>
          </Modal.Header>
          <Modal.Body>
            {formError && <Alert variant="danger">{formError}</Alert>}
            <Form.Group className="mb-3">
              <Form.Label>{t('Permission code')}</Form.Label>
              <Form.Control
                type="text"
                value={form.code}
                onChange={(e) => setForm((f) => ({ ...f, code: e.target.value }))}
                placeholder="e.g. media:view"
                autoFocus
                required
                data-testid="permission-form-code"
              />
            </Form.Group>
            <Form.Group>
              <Form.Label>{t('Detail')}</Form.Label>
              <Form.Control
                type="text"
                value={form.detail}
                onChange={(e) => setForm((f) => ({ ...f, detail: e.target.value }))}
                placeholder={t('Optional description')}
                data-testid="permission-form-detail"
              />
            </Form.Group>
          </Modal.Body>
          <Modal.Footer>
            <Button variant="secondary" onClick={() => setShowForm(false)}>{t('Cancel')}</Button>
            <Button type="submit" variant="primary" disabled={submitting} data-testid="permission-form-submit">
              {submitting ? <Spinner size="sm" animation="border" /> : t('Save')}
            </Button>
          </Modal.Footer>
        </Form>
      </Modal>

      <Modal show={!!deleteTarget} onHide={() => setDeleteTarget(null)} centered>
        <Modal.Header closeButton><Modal.Title>{t('Delete Permission')}</Modal.Title></Modal.Header>
        <Modal.Body>{t('Delete permission "{{code}}"?', { code: deleteTarget?.code })}</Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setDeleteTarget(null)}>{t('Cancel')}</Button>
          <Button variant="danger" onClick={confirmDelete} disabled={deleting} data-testid="permission-delete-confirm">
            {deleting ? <Spinner size="sm" animation="border" /> : t('Delete')}
          </Button>
        </Modal.Footer>
      </Modal>
    </Container>
  );
};

export default PermissionsPage;

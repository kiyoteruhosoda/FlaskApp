import React, { useCallback, useEffect, useState } from 'react';
import {
  Container, Row, Col, Table, Button, Form, Spinner, Alert, Badge, Modal,
} from 'react-bootstrap';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../services/api';
import { AdminRole, AdminRoleDetail, AdminPermission } from '../types/api';
import { getApiErrorCode } from '../services/apiErrors';

const RolesPage: React.FC = () => {
  const { t } = useTranslation();
  const [roles, setRoles] = useState<AdminRole[]>([]);
  const [permissions, setPermissions] = useState<AdminPermission[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [showForm, setShowForm] = useState(false);
  const [editTarget, setEditTarget] = useState<AdminRoleDetail | null>(null);
  const [form, setForm] = useState({ name: '', permissionIds: [] as number[] });
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [deleteTarget, setDeleteTarget] = useState<AdminRole | null>(null);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    // 権限一覧の取得失敗（403 等）でロール一覧まで巻き込まないよう分離する。
    // 権限一覧が無い場合はロールの閲覧のみ可能で、紐づけ編集が制限される。
    const [rolesRes, permsRes] = await Promise.allSettled([
      apiClient.getAdminRoles(),
      apiClient.getAdminPermissions(),
    ]);
    if (rolesRes.status === 'fulfilled') {
      setRoles(rolesRes.value.roles);
    } else {
      const e: any = rolesRes.reason;
      setError(e?.response?.status === 403 ? t('You do not have permission to manage roles') : t('Failed to load roles'));
    }
    if (permsRes.status === 'fulfilled') {
      setPermissions(permsRes.value.permissions);
    } else {
      setPermissions([]);
    }
    setLoading(false);
  }, [t]);

  useEffect(() => { load(); }, [load]);

  const openCreate = () => {
    setEditTarget(null);
    setForm({ name: '', permissionIds: [] });
    setFormError(null);
    setShowForm(true);
  };

  const openEdit = async (role: AdminRole) => {
    try {
      const res = await apiClient.getAdminRoleDetail(role.id);
      setEditTarget(res.role);
      setForm({ name: res.role.name, permissionIds: res.role.permissions.map((p) => p.id) });
    } catch {
      setEditTarget({ ...role, permissions: role.permissions.map((code, i) => ({ id: i, code })), userCount: 0 });
      setForm({ name: role.name, permissionIds: [] });
    }
    setFormError(null);
    setShowForm(true);
  };

  const togglePerm = (id: number) => {
    setForm((f) => ({
      ...f,
      permissionIds: f.permissionIds.includes(id)
        ? f.permissionIds.filter((x) => x !== id)
        : [...f.permissionIds, id],
    }));
  };

  const submitForm = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) { setFormError(t('Role name is required')); return; }
    setSubmitting(true);
    setFormError(null);
    try {
      if (editTarget) {
        const res = await apiClient.updateAdminRole(editTarget.id, {
          name: form.name.trim(), permissionIds: form.permissionIds,
        });
        setRoles((prev) => prev.map((r) => r.id === editTarget.id
          ? { ...r, name: res.role.name, permissions: res.role.permissions.map((p) => p.code) }
          : r));
      } else {
        const res = await apiClient.createAdminRole({ name: form.name.trim(), permissionIds: form.permissionIds });
        setRoles((prev) => [...prev, { id: res.role.id, name: res.role.name, permissions: res.role.permissions.map((p) => p.code) }]);
      }
      setShowForm(false);
    } catch (e: any) {
      const code = getApiErrorCode(e);
      setFormError(code === 'name_exists' ? t('Role name already in use') : t('Failed to save role'));
    } finally {
      setSubmitting(false);
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await apiClient.deleteAdminRole(deleteTarget.id);
      setRoles((prev) => prev.filter((r) => r.id !== deleteTarget.id));
      setDeleteTarget(null);
    } catch (e: any) {
      setError(e?.response?.data?.message || t('Failed to delete role'));
      setDeleteTarget(null);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <Container fluid className="py-4" data-testid="roles-page">
      <Row className="mb-3 align-items-center">
        <Col>
          <h1 className="h3 mb-1">{t('Role Management')}</h1>
          <p className="text-muted mb-0">{t('Manage roles and their permissions')}</p>
        </Col>
        <Col xs="auto">
          <Button variant="primary" onClick={openCreate} data-testid="roles-create">
            <i className="fa-solid fa-plus me-1" />{t('New Role')}
          </Button>
        </Col>
      </Row>

      {error && <Alert variant="danger" dismissible onClose={() => setError(null)}>{error}</Alert>}

      {loading ? (
        <div className="text-center py-5"><Spinner animation="border" /></div>
      ) : roles.length === 0 ? (
        <div className="text-center text-muted py-5" data-testid="roles-empty">{t('No roles found')}</div>
      ) : (
        <Table hover className="align-middle" data-testid="roles-table">
          <thead>
            <tr>
              <th>{t('Name')}</th>
              <th>{t('Permissions')}</th>
              <th>{t('Actions')}</th>
            </tr>
          </thead>
          <tbody>
            {roles.map((r) => (
              <tr key={r.id} data-testid="role-row">
                <td className="fw-semibold">
                  {r.name}
                  {r.isDefault && (
                    <Badge bg="info" className="ms-2" data-testid="role-default-badge">
                      {t('Default')}
                    </Badge>
                  )}
                </td>
                <td>
                  <div className="d-flex flex-wrap gap-1">
                    {r.permissions.slice(0, 4).map((p) => (
                      <Badge key={p} bg="light" text="dark" className="border">{p}</Badge>
                    ))}
                    {r.permissions.length > 4 && (
                      <Badge bg="secondary">+{r.permissions.length - 4}</Badge>
                    )}
                    {r.permissions.length === 0 && <span className="text-muted small">—</span>}
                  </div>
                </td>
                <td>
                  {r.isDefault ? (
                    <span className="text-muted small">{t('Default roles cannot be edited')}</span>
                  ) : (
                    <div className="d-flex gap-1">
                      <Button size="sm" variant="outline-secondary" onClick={() => openEdit(r)} data-testid="role-edit">
                        <i className="fa-solid fa-pen" />
                      </Button>
                      <Button size="sm" variant="outline-danger" onClick={() => setDeleteTarget(r)} data-testid="role-delete">
                        <i className="fa-solid fa-trash" />
                      </Button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}

      <Modal show={showForm} onHide={() => setShowForm(false)} centered>
        <Form onSubmit={submitForm}>
          <Modal.Header closeButton>
            <Modal.Title>{editTarget ? t('Edit Role') : t('New Role')}</Modal.Title>
          </Modal.Header>
          <Modal.Body>
            {formError && <Alert variant="danger">{formError}</Alert>}
            <Form.Group className="mb-3">
              <Form.Label>{t('Role name')}</Form.Label>
              <Form.Control
                type="text"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                autoFocus
                required
                data-testid="role-form-name"
              />
            </Form.Group>
            {permissions.length > 0 ? (
              <Form.Group>
                <Form.Label>{t('Permissions')}</Form.Label>
                <div style={{ maxHeight: 240, overflowY: 'auto' }} className="border rounded p-2" data-testid="role-permissions-list">
                  {permissions.map((p) => (
                    <Form.Check
                      key={p.id}
                      type="checkbox"
                      id={`perm-${p.id}`}
                      label={<><span className="fw-mono">{p.code}</span>{p.detail && <span className="text-muted ms-2 small">— {p.detail}</span>}</>}
                      checked={form.permissionIds.includes(p.id)}
                      onChange={() => togglePerm(p.id)}
                    />
                  ))}
                </div>
              </Form.Group>
            ) : (
              <Alert variant="warning" className="mb-0">
                {t('Permission list is unavailable, so permission assignment cannot be edited here.')}
              </Alert>
            )}
          </Modal.Body>
          <Modal.Footer>
            <Button variant="secondary" onClick={() => setShowForm(false)}>{t('Cancel')}</Button>
            <Button type="submit" variant="primary" disabled={submitting} data-testid="role-form-submit">
              {submitting ? <Spinner size="sm" animation="border" /> : t('Save')}
            </Button>
          </Modal.Footer>
        </Form>
      </Modal>

      <Modal show={!!deleteTarget} onHide={() => setDeleteTarget(null)} centered>
        <Modal.Header closeButton><Modal.Title>{t('Delete Role')}</Modal.Title></Modal.Header>
        <Modal.Body>{t('Delete role "{{name}}"?', { name: deleteTarget?.name })}</Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setDeleteTarget(null)}>{t('Cancel')}</Button>
          <Button variant="danger" onClick={confirmDelete} disabled={deleting} data-testid="role-delete-confirm">
            {deleting ? <Spinner size="sm" animation="border" /> : t('Delete')}
          </Button>
        </Modal.Footer>
      </Modal>
    </Container>
  );
};

export default RolesPage;

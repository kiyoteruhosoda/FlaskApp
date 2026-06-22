import React, { useCallback, useEffect, useState } from 'react';
import {
  Container,
  Row,
  Col,
  Table,
  Button,
  Form,
  Spinner,
  Alert,
  Badge,
  Modal,
} from 'react-bootstrap';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../services/api';
import { AdminUser, AdminRole } from '../types/api';

const UsersPage: React.FC = () => {
  const { t } = useTranslation();

  const [users, setUsers] = useState<AdminUser[]>([]);
  const [roles, setRoles] = useState<AdminRole[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');

  // create/edit modal
  const [showForm, setShowForm] = useState(false);
  const [editTarget, setEditTarget] = useState<AdminUser | null>(null);
  const [form, setForm] = useState({
    email: '',
    username: '',
    password: '',
    isActive: true,
    roleIds: [] as number[],
  });
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // roles modal
  const [showRoles, setShowRoles] = useState(false);
  const [rolesTarget, setRolesTarget] = useState<AdminUser | null>(null);
  const [editRoleIds, setEditRoleIds] = useState<number[]>([]);
  const [savingRoles, setSavingRoles] = useState(false);
  const [rolesError, setRolesError] = useState<string | null>(null);

  // delete confirm
  const [deleteTarget, setDeleteTarget] = useState<AdminUser | null>(null);
  const [deleting, setDeleting] = useState(false);

  const loadData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [usersRes, rolesRes] = await Promise.all([
        apiClient.getAdminUsers({ q: query || undefined }),
        apiClient.getAdminRoles(),
      ]);
      setUsers(usersRes.users);
      setRoles(rolesRes.roles);
    } catch (e: any) {
      const status = e?.response?.status;
      if (status === 403) {
        setError(t('You do not have permission to manage users'));
      } else {
        setError(e?.response?.data?.message || e?.message || t('Failed to load users'));
      }
    } finally {
      setIsLoading(false);
    }
  }, [query, t]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const submitSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setQuery(search.trim());
  };

  const openCreate = () => {
    setEditTarget(null);
    setForm({ email: '', username: '', password: '', isActive: true, roleIds: [] });
    setFormError(null);
    setShowForm(true);
  };

  const openEdit = (user: AdminUser) => {
    setEditTarget(user);
    setForm({
      email: user.email,
      username: user.username || '',
      password: '',
      isActive: user.isActive,
      roleIds: user.roles.map((r) => r.id),
    });
    setFormError(null);
    setShowForm(true);
  };

  const toggleFormRole = (roleId: number) => {
    setForm((f) => ({
      ...f,
      roleIds: f.roleIds.includes(roleId)
        ? f.roleIds.filter((id) => id !== roleId)
        : [...f.roleIds, roleId],
    }));
  };

  const submitForm = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.email.trim()) {
      setFormError(t('Email is required'));
      return;
    }
    if (!editTarget && !form.password.trim()) {
      setFormError(t('Password is required'));
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      if (editTarget) {
        const payload: any = {
          email: form.email.trim(),
          username: form.username.trim() || null,
          isActive: form.isActive,
        };
        const updated = await apiClient.updateAdminUser(editTarget.id, payload);
        if (form.roleIds.length > 0) {
          const withRoles = await apiClient.updateAdminUserRoles(editTarget.id, form.roleIds);
          setUsers((prev) => prev.map((u) => (u.id === editTarget.id ? withRoles.user : u)));
        } else {
          setUsers((prev) => prev.map((u) => (u.id === editTarget.id ? updated.user : u)));
        }
      } else {
        const created = await apiClient.createAdminUser({
          email: form.email.trim(),
          username: form.username.trim() || undefined,
          password: form.password,
          roleIds: form.roleIds,
        });
        setUsers((prev) => [...prev, created.user]);
      }
      setShowForm(false);
    } catch (e: any) {
      const code = e?.response?.data?.error;
      if (code === 'email_exists') {
        setFormError(t('Email already in use'));
      } else {
        setFormError(e?.response?.data?.message || e?.message || t('Failed to save user'));
      }
    } finally {
      setSubmitting(false);
    }
  };

  const openRoles = (user: AdminUser) => {
    setRolesTarget(user);
    setEditRoleIds(user.roles.map((r) => r.id));
    setRolesError(null);
    setShowRoles(true);
  };

  const toggleRole = (roleId: number) => {
    setEditRoleIds((prev) =>
      prev.includes(roleId) ? prev.filter((id) => id !== roleId) : [...prev, roleId]
    );
  };

  const saveRoles = async () => {
    if (!rolesTarget) return;
    if (editRoleIds.length === 0) {
      setRolesError(t('At least one role is required'));
      return;
    }
    setSavingRoles(true);
    setRolesError(null);
    try {
      const res = await apiClient.updateAdminUserRoles(rolesTarget.id, editRoleIds);
      setUsers((prev) => prev.map((u) => (u.id === rolesTarget.id ? res.user : u)));
      setShowRoles(false);
    } catch (e: any) {
      setRolesError(e?.response?.data?.message || e?.message || t('Failed to update roles'));
    } finally {
      setSavingRoles(false);
    }
  };

  const resetTOTP = async (user: AdminUser) => {
    if (!window.confirm(t('Reset TOTP for {{email}}?', { email: user.email }))) return;
    try {
      await apiClient.resetAdminUserTOTP(user.id);
      setUsers((prev) =>
        prev.map((u) => (u.id === user.id ? { ...u, hasTOTP: false } : u))
      );
    } catch (e: any) {
      setError(e?.response?.data?.message || e?.message || t('Failed to reset TOTP'));
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await apiClient.deleteAdminUser(deleteTarget.id);
      setUsers((prev) => prev.filter((u) => u.id !== deleteTarget.id));
      setDeleteTarget(null);
    } catch (e: any) {
      const code = e?.response?.data?.error;
      if (code === 'cannot_delete_self') {
        setError(t('Cannot delete yourself'));
      } else {
        setError(e?.response?.data?.message || e?.message || t('Failed to delete user'));
      }
      setDeleteTarget(null);
    } finally {
      setDeleting(false);
    }
  };

  const filtered = query
    ? users.filter(
        (u) =>
          u.email.toLowerCase().includes(query.toLowerCase()) ||
          (u.username || '').toLowerCase().includes(query.toLowerCase())
      )
    : users;

  return (
    <Container fluid className="py-4" data-testid="users-page">
      <Row className="mb-3 align-items-center">
        <Col>
          <h1 className="h3 mb-1">{t('User Management')}</h1>
          <p className="text-muted mb-0">{t('Manage users, roles and access')}</p>
        </Col>
        <Col xs="auto" className="d-flex gap-2">
          <Form className="d-flex" onSubmit={submitSearch}>
            <Form.Control
              type="search"
              placeholder={t('Search users')}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              data-testid="users-search"
            />
            <Button type="submit" variant="outline-primary" className="ms-2">{t('Search')}</Button>
          </Form>
          <Button variant="primary" onClick={openCreate} data-testid="users-create">
            <i className="bi bi-plus-lg me-1" />{t('New User')}
          </Button>
        </Col>
      </Row>

      {error && (
        <Alert variant="danger" dismissible onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {isLoading ? (
        <div className="text-center py-5"><Spinner animation="border" /></div>
      ) : filtered.length === 0 ? (
        <div className="text-center text-muted py-5" data-testid="users-empty">
          {t('No users found')}
        </div>
      ) : (
        <div className="table-responsive">
          <Table hover className="align-middle" data-testid="users-table">
            <thead>
              <tr>
                <th>{t('Email')}</th>
                <th>{t('Username')}</th>
                <th>{t('Roles')}</th>
                <th>{t('Status')}</th>
                <th>{t('TOTP')}</th>
                <th>{t('Actions')}</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((u) => (
                <tr key={u.id} data-testid="user-row">
                  <td>{u.email}</td>
                  <td className="text-muted">{u.username || '—'}</td>
                  <td>
                    <div className="d-flex flex-wrap gap-1">
                      {u.roles.map((r) => (
                        <Badge key={r.id} bg="primary">{r.name}</Badge>
                      ))}
                      {u.roles.length === 0 && <span className="text-muted small">—</span>}
                    </div>
                  </td>
                  <td>
                    <Badge bg={u.isActive ? 'success' : 'secondary'}>
                      {u.isActive ? t('Active') : t('Inactive')}
                    </Badge>
                  </td>
                  <td>
                    {u.hasTOTP ? (
                      <Badge bg="info">{t('Enabled')}</Badge>
                    ) : (
                      <span className="text-muted small">—</span>
                    )}
                  </td>
                  <td>
                    <div className="d-flex gap-1 flex-wrap">
                      <Button size="sm" variant="outline-secondary" onClick={() => openEdit(u)} data-testid="user-edit">
                        <i className="bi bi-pencil" />
                      </Button>
                      <Button size="sm" variant="outline-primary" onClick={() => openRoles(u)} data-testid="user-roles">
                        <i className="bi bi-shield" />
                      </Button>
                      {u.hasTOTP && (
                        <Button size="sm" variant="outline-warning" onClick={() => resetTOTP(u)} title={t('Reset TOTP')} data-testid="user-reset-totp">
                          <i className="bi bi-shield-x" />
                        </Button>
                      )}
                      <Button size="sm" variant="outline-danger" onClick={() => setDeleteTarget(u)} data-testid="user-delete">
                        <i className="bi bi-trash" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        </div>
      )}

      {/* Create / Edit User Modal */}
      <Modal show={showForm} onHide={() => setShowForm(false)} centered>
        <Form onSubmit={submitForm}>
          <Modal.Header closeButton>
            <Modal.Title>{editTarget ? t('Edit User') : t('New User')}</Modal.Title>
          </Modal.Header>
          <Modal.Body>
            {formError && <Alert variant="danger">{formError}</Alert>}
            <Form.Group className="mb-3">
              <Form.Label>{t('Email')}</Form.Label>
              <Form.Control
                type="email"
                value={form.email}
                onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
                required
                autoFocus
                data-testid="user-form-email"
              />
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>{t('Username')}</Form.Label>
              <Form.Control
                type="text"
                value={form.username}
                onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))}
                data-testid="user-form-username"
              />
            </Form.Group>
            {!editTarget && (
              <Form.Group className="mb-3">
                <Form.Label>{t('Password')}</Form.Label>
                <Form.Control
                  type="password"
                  value={form.password}
                  onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
                  required
                  data-testid="user-form-password"
                />
              </Form.Group>
            )}
            <Form.Group className="mb-3">
              <Form.Check
                type="checkbox"
                label={t('Active')}
                checked={form.isActive}
                onChange={(e) => setForm((f) => ({ ...f, isActive: e.target.checked }))}
              />
            </Form.Group>
            {roles.length > 0 && (
              <Form.Group>
                <Form.Label>{t('Roles')}</Form.Label>
                <div className="d-flex flex-wrap gap-2">
                  {roles.map((r) => (
                    <Form.Check
                      key={r.id}
                      type="checkbox"
                      id={`form-role-${r.id}`}
                      label={r.name}
                      checked={form.roleIds.includes(r.id)}
                      onChange={() => toggleFormRole(r.id)}
                    />
                  ))}
                </div>
              </Form.Group>
            )}
          </Modal.Body>
          <Modal.Footer>
            <Button variant="secondary" onClick={() => setShowForm(false)}>{t('Cancel')}</Button>
            <Button type="submit" variant="primary" disabled={submitting} data-testid="user-form-submit">
              {submitting ? <Spinner size="sm" animation="border" /> : t('Save')}
            </Button>
          </Modal.Footer>
        </Form>
      </Modal>

      {/* Edit Roles Modal */}
      <Modal show={showRoles} onHide={() => setShowRoles(false)} centered>
        <Modal.Header closeButton>
          <Modal.Title>{t('Edit Roles')}: {rolesTarget?.email}</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {rolesError && <Alert variant="danger">{rolesError}</Alert>}
          <div className="d-flex flex-column gap-2">
            {roles.map((r) => (
              <Form.Check
                key={r.id}
                type="checkbox"
                id={`roles-modal-${r.id}`}
                label={
                  <span>
                    <strong>{r.name}</strong>
                    {r.permissions.length > 0 && (
                      <span className="text-muted ms-2 small">
                        ({r.permissions.slice(0, 3).join(', ')}{r.permissions.length > 3 ? '…' : ''})
                      </span>
                    )}
                  </span>
                }
                checked={editRoleIds.includes(r.id)}
                onChange={() => toggleRole(r.id)}
              />
            ))}
          </div>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setShowRoles(false)}>{t('Cancel')}</Button>
          <Button variant="primary" onClick={saveRoles} disabled={savingRoles} data-testid="roles-save">
            {savingRoles ? <Spinner size="sm" animation="border" /> : t('Save')}
          </Button>
        </Modal.Footer>
      </Modal>

      {/* Delete Confirm */}
      <Modal show={!!deleteTarget} onHide={() => setDeleteTarget(null)} centered>
        <Modal.Header closeButton>
          <Modal.Title>{t('Delete User')}</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {t('Delete user "{{email}}"? This cannot be undone.', { email: deleteTarget?.email })}
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setDeleteTarget(null)}>{t('Cancel')}</Button>
          <Button variant="danger" onClick={confirmDelete} disabled={deleting} data-testid="user-delete-confirm">
            {deleting ? <Spinner size="sm" animation="border" /> : t('Delete')}
          </Button>
        </Modal.Footer>
      </Modal>
    </Container>
  );
};

export default UsersPage;

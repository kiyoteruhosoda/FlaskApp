import React, { useCallback, useEffect, useState } from 'react';
import {
  Container, Row, Col, Table, Button, Form, Spinner, Alert, Badge, Modal, ListGroup,
} from 'react-bootstrap';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../services/api';
import { AdminGroup, AdminUser } from '../types/api';
import { getApiErrorCode } from '../services/apiErrors';

const GroupsPage: React.FC = () => {
  const { t } = useTranslation();
  const [groups, setGroups] = useState<AdminGroup[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [showForm, setShowForm] = useState(false);
  const [editTarget, setEditTarget] = useState<AdminGroup | null>(null);
  const [form, setForm] = useState({ name: '', description: '', parentId: '' });
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [deleteTarget, setDeleteTarget] = useState<AdminGroup | null>(null);
  const [deleting, setDeleting] = useState(false);

  // メンバー管理モーダル
  const [showMembers, setShowMembers] = useState(false);
  const [membersTarget, setMembersTarget] = useState<AdminGroup | null>(null);
  const [allUsers, setAllUsers] = useState<AdminUser[]>([]);
  const [memberIds, setMemberIds] = useState<number[]>([]);
  const [loadingMembers, setLoadingMembers] = useState(false);
  const [savingMembers, setSavingMembers] = useState(false);
  const [membersError, setMembersError] = useState<string | null>(null);
  const [memberSearch, setMemberSearch] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.getAdminGroups();
      setGroups(res.groups);
    } catch (e: any) {
      setError(e?.response?.status === 403 ? t('You do not have permission to manage groups') : t('Failed to load groups'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => { load(); }, [load]);

  const openCreate = () => {
    setEditTarget(null);
    setForm({ name: '', description: '', parentId: '' });
    setFormError(null);
    setShowForm(true);
  };

  const openEdit = (group: AdminGroup) => {
    setEditTarget(group);
    setForm({
      name: group.name,
      description: group.description || '',
      parentId: group.parentId ? String(group.parentId) : '',
    });
    setFormError(null);
    setShowForm(true);
  };

  const submitForm = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) { setFormError(t('Group name is required')); return; }
    setSubmitting(true);
    setFormError(null);
    const parentId = form.parentId ? Number(form.parentId) : null;
    try {
      if (editTarget) {
        const res = await apiClient.updateAdminGroup(editTarget.id, {
          name: form.name.trim(),
          description: form.description.trim() || undefined,
          parentId,
        });
        setGroups((prev) => prev.map((g) => g.id === editTarget.id ? res.group : g));
      } else {
        const res = await apiClient.createAdminGroup({
          name: form.name.trim(),
          description: form.description.trim() || undefined,
          parentId,
        });
        setGroups((prev) => [...prev, res.group]);
      }
      setShowForm(false);
    } catch (e: any) {
      const code = getApiErrorCode(e);
      if (code === 'name_exists') setFormError(t('Group name already in use'));
      else if (code === 'hierarchy_error') setFormError(e?.response?.data?.message || t('Invalid group hierarchy'));
      else setFormError(t('Failed to save group'));
    } finally {
      setSubmitting(false);
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await apiClient.deleteAdminGroup(deleteTarget.id);
      setGroups((prev) => prev.filter((g) => g.id !== deleteTarget.id));
      setDeleteTarget(null);
    } catch (e: any) {
      const code = getApiErrorCode(e);
      setError(code === 'has_children' ? t('Remove child groups first') : t('Failed to delete group'));
      setDeleteTarget(null);
    } finally {
      setDeleting(false);
    }
  };

  const openMembers = async (group: AdminGroup) => {
    setMembersTarget(group);
    setMembersError(null);
    setMemberSearch('');
    setShowMembers(true);
    setLoadingMembers(true);
    try {
      const [detailRes, usersRes] = await Promise.all([
        apiClient.getAdminGroupDetail(group.id),
        apiClient.getAdminUsers(),
      ]);
      setAllUsers(usersRes.users);
      setMemberIds(detailRes.group.members.map((m) => m.id));
    } catch (e: any) {
      setMembersError(t('Failed to load group members'));
    } finally {
      setLoadingMembers(false);
    }
  };

  const toggleMember = (userId: number) => {
    setMemberIds((prev) =>
      prev.includes(userId) ? prev.filter((id) => id !== userId) : [...prev, userId]
    );
  };

  const saveMembers = async () => {
    if (!membersTarget) return;
    setSavingMembers(true);
    setMembersError(null);
    try {
      const res = await apiClient.updateAdminGroup(membersTarget.id, { memberIds });
      setGroups((prev) => prev.map((g) => g.id === membersTarget.id ? res.group : g));
      setShowMembers(false);
    } catch (e: any) {
      setMembersError(e?.response?.data?.message || t('Failed to save members'));
    } finally {
      setSavingMembers(false);
    }
  };

  const filteredUsers = memberSearch.trim()
    ? allUsers.filter((u) =>
        u.email.toLowerCase().includes(memberSearch.toLowerCase()) ||
        (u.username || '').toLowerCase().includes(memberSearch.toLowerCase())
      )
    : allUsers;

  const availableParents = groups.filter((g) => !editTarget || g.id !== editTarget.id);

  return (
    <Container fluid className="py-4" data-testid="groups-page">
      <Row className="mb-3 align-items-center">
        <Col>
          <h1 className="h3 mb-1">{t('Group Management')}</h1>
          <p className="text-muted mb-0">{t('Manage user groups and hierarchy')}</p>
        </Col>
        <Col xs="auto">
          <Button variant="primary" onClick={openCreate} data-testid="groups-create">
            <i className="fa-solid fa-plus me-1" />{t('New Group')}
          </Button>
        </Col>
      </Row>

      {error && <Alert variant="danger" dismissible onClose={() => setError(null)}>{error}</Alert>}

      {loading ? (
        <div className="text-center py-5"><Spinner animation="border" /></div>
      ) : groups.length === 0 ? (
        <div className="text-center text-muted py-5" data-testid="groups-empty">{t('No groups found')}</div>
      ) : (
        <Table hover className="align-middle" data-testid="groups-table">
          <thead>
            <tr>
              <th>{t('Name')}</th>
              <th>{t('Parent')}</th>
              <th>{t('Members')}</th>
              <th>{t('Actions')}</th>
            </tr>
          </thead>
          <tbody>
            {groups.map((g) => (
              <tr key={g.id} data-testid="group-row">
                <td className="fw-semibold">{g.name}</td>
                <td className="text-muted">{g.parentName || '—'}</td>
                <td><Badge bg="secondary">{g.memberCount}</Badge></td>
                <td>
                  <div className="d-flex gap-1">
                    <Button size="sm" variant="outline-primary" onClick={() => openMembers(g)} data-testid="group-members" title={t('Manage Members')}>
                      <i className="fa-solid fa-users" />
                    </Button>
                    <Button size="sm" variant="outline-secondary" onClick={() => openEdit(g)} data-testid="group-edit">
                      <i className="fa-solid fa-pen" />
                    </Button>
                    <Button size="sm" variant="outline-danger" onClick={() => setDeleteTarget(g)} data-testid="group-delete">
                      <i className="fa-solid fa-trash" />
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}

      {/* Create / Edit Group Modal */}
      <Modal show={showForm} onHide={() => setShowForm(false)} centered>
        <Form onSubmit={submitForm}>
          <Modal.Header closeButton>
            <Modal.Title>{editTarget ? t('Edit Group') : t('New Group')}</Modal.Title>
          </Modal.Header>
          <Modal.Body>
            {formError && <Alert variant="danger">{formError}</Alert>}
            <Form.Group className="mb-3">
              <Form.Label>{t('Group name')}</Form.Label>
              <Form.Control
                type="text"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                autoFocus
                required
                data-testid="group-form-name"
              />
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>{t('Description')}</Form.Label>
              <Form.Control
                type="text"
                value={form.description}
                onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              />
            </Form.Group>
            <Form.Group>
              <Form.Label>{t('Parent Group')}</Form.Label>
              <Form.Select
                value={form.parentId}
                onChange={(e) => setForm((f) => ({ ...f, parentId: e.target.value }))}
                data-testid="group-form-parent"
              >
                <option value="">{t('No parent (root group)')}</option>
                {availableParents.map((g) => (
                  <option key={g.id} value={g.id}>{g.name}</option>
                ))}
              </Form.Select>
            </Form.Group>
          </Modal.Body>
          <Modal.Footer>
            <Button variant="secondary" onClick={() => setShowForm(false)}>{t('Cancel')}</Button>
            <Button type="submit" variant="primary" disabled={submitting} data-testid="group-form-submit">
              {submitting ? <Spinner size="sm" animation="border" /> : t('Save')}
            </Button>
          </Modal.Footer>
        </Form>
      </Modal>

      {/* Delete Confirm Modal */}
      <Modal show={!!deleteTarget} onHide={() => setDeleteTarget(null)} centered>
        <Modal.Header closeButton><Modal.Title>{t('Delete Group')}</Modal.Title></Modal.Header>
        <Modal.Body>{t('Delete group "{{name}}"?', { name: deleteTarget?.name })}</Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setDeleteTarget(null)}>{t('Cancel')}</Button>
          <Button variant="danger" onClick={confirmDelete} disabled={deleting} data-testid="group-delete-confirm">
            {deleting ? <Spinner size="sm" animation="border" /> : t('Delete')}
          </Button>
        </Modal.Footer>
      </Modal>

      {/* Members Management Modal */}
      <Modal show={showMembers} onHide={() => setShowMembers(false)} centered size="lg">
        <Modal.Header closeButton>
          <Modal.Title>{t('Manage Members')}: {membersTarget?.name}</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {membersError && <Alert variant="danger">{membersError}</Alert>}
          {loadingMembers ? (
            <div className="text-center py-3"><Spinner animation="border" /></div>
          ) : (
            <>
              <Form.Control
                type="search"
                placeholder={t('Search users')}
                value={memberSearch}
                onChange={(e) => setMemberSearch(e.target.value)}
                className="mb-3"
                data-testid="members-search"
              />
              <div style={{ maxHeight: 400, overflowY: 'auto' }}>
                <ListGroup variant="flush">
                  {filteredUsers.map((u) => (
                    <ListGroup.Item key={u.id} className="d-flex align-items-center gap-2 px-0">
                      <Form.Check
                        type="checkbox"
                        id={`member-${u.id}`}
                        checked={memberIds.includes(u.id)}
                        onChange={() => toggleMember(u.id)}
                        data-testid={`member-check-${u.id}`}
                      />
                      <label htmlFor={`member-${u.id}`} className="flex-grow-1 mb-0" style={{ cursor: 'pointer' }}>
                        <span className="fw-semibold">{u.username || u.email}</span>
                        {u.username && <span className="text-muted ms-2 small">{u.email}</span>}
                      </label>
                      {memberIds.includes(u.id) && <Badge bg="primary">{t('Member')}</Badge>}
                    </ListGroup.Item>
                  ))}
                  {filteredUsers.length === 0 && (
                    <ListGroup.Item className="text-muted text-center px-0">{t('No users found')}</ListGroup.Item>
                  )}
                </ListGroup>
              </div>
              <div className="mt-2 text-muted small">
                {t('{{count}} member(s) selected', { count: memberIds.length })}
              </div>
            </>
          )}
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setShowMembers(false)}>{t('Cancel')}</Button>
          <Button variant="primary" onClick={saveMembers} disabled={savingMembers || loadingMembers} data-testid="members-save">
            {savingMembers ? <Spinner size="sm" animation="border" /> : t('Save')}
          </Button>
        </Modal.Footer>
      </Modal>
    </Container>
  );
};

export default GroupsPage;

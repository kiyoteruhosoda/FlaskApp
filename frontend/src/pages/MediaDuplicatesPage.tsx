import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Container,
  Row,
  Col,
  Card,
  Button,
  Spinner,
  Alert,
  Badge,
  Form,
  Modal,
} from 'react-bootstrap';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../services/api';
import { DuplicateGroup } from '../types/api';

function formatBytes(bytes: number | null): string {
  if (!bytes || bytes <= 0) return '-';
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

const MediaDuplicatesPage: React.FC = () => {
  const { t } = useTranslation();

  const [groups, setGroups] = useState<DuplicateGroup[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // group key -> media id を「残す」対象として選択（既定は各グループ先頭＝最古取込）
  const [keepByGroup, setKeepByGroup] = useState<Record<string, number>>({});
  const [pendingGroup, setPendingGroup] = useState<DuplicateGroup | null>(null);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiClient.getMediaDuplicates(200);
      setGroups(data.groups || []);
      const defaults: Record<string, number> = {};
      (data.groups || []).forEach((g) => {
        if (g.items.length > 0) defaults[g.key] = g.items[0].id;
      });
      setKeepByGroup(defaults);
    } catch (e: any) {
      setError(e?.response?.data?.message || t('Failed to load duplicates.'));
    } finally {
      setIsLoading(false);
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  const totalRedundant = useMemo(
    () => groups.reduce((sum, g) => sum + Math.max(0, g.items.length - 1), 0),
    [groups]
  );

  const deleteOthers = async (group: DuplicateGroup) => {
    const keepId = keepByGroup[group.key];
    const deleteIds = group.items.map((it) => it.id).filter((id) => id !== keepId);
    if (deleteIds.length === 0) return;
    setDeleting(true);
    setError(null);
    try {
      await apiClient.bulkDeleteMedia(deleteIds);
      // 削除したグループを一覧から除去
      setGroups((prev) => prev.filter((g) => g.key !== group.key));
    } catch (e: any) {
      setError(e?.response?.data?.message || t('Failed to delete media.'));
    } finally {
      setDeleting(false);
      setPendingGroup(null);
    }
  };

  return (
    <Container className="py-4" data-testid="media-duplicates-page">
      <div className="d-flex justify-content-between align-items-center mb-3">
        <div>
          <h3 className="mb-1">{t('Duplicate media')}</h3>
          <div className="text-muted small">
            {t('Review duplicate groups and keep one. Deleting is a soft delete; originals remain on storage.')}
          </div>
        </div>
        <Button variant="outline-secondary" onClick={load} disabled={isLoading}>
          <i className="fa-solid fa-rotate-right me-1" />
          {t('Refresh')}
        </Button>
      </div>

      {error && (
        <Alert variant="danger" onClose={() => setError(null)} dismissible>
          {error}
        </Alert>
      )}

      {!isLoading && groups.length > 0 && (
        <Alert variant="info" className="py-2">
          {t('{{groups}} groups, {{redundant}} redundant files', {
            groups: groups.length,
            redundant: totalRedundant,
          })}
        </Alert>
      )}

      {isLoading ? (
        <div className="text-center py-5">
          <Spinner animation="border" />
        </div>
      ) : groups.length === 0 ? (
        <Alert variant="success">{t('No duplicates found.')}</Alert>
      ) : (
        groups.map((group) => {
          const keepId = keepByGroup[group.key];
          return (
            <Card key={group.key} className="mb-3">
              <Card.Header className="d-flex justify-content-between align-items-center">
                <div>
                  <Badge bg={group.match_type === 'exact' ? 'danger' : 'warning'} className="me-2">
                    {group.match_type === 'exact' ? t('Exact match') : t('Similar')}
                  </Badge>
                  <span className="text-muted small">{group.count} {t('items')}</span>
                </div>
                <Button
                  size="sm"
                  variant="danger"
                  disabled={deleting}
                  onClick={() => setPendingGroup(group)}
                >
                  <i className="fa-solid fa-trash me-1" />
                  {t('Delete the others')}
                </Button>
              </Card.Header>
              <Card.Body>
                <Row className="g-3">
                  {group.items.map((item) => {
                    const isKeep = item.id === keepId;
                    return (
                      <Col key={item.id} xs={6} md={3} lg={2}>
                        <Card className={isKeep ? 'border-success' : 'border-light'}>
                          <div style={{ aspectRatio: '1 / 1', overflow: 'hidden', background: '#f2f2f2' }}>
                            <img
                              src={item.thumbnail_url}
                              alt={item.filename || String(item.id)}
                              style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                              loading="lazy"
                            />
                          </div>
                          <Card.Body className="p-2">
                            <Form.Check
                              type="radio"
                              name={`keep-${group.key}`}
                              id={`keep-${group.key}-${item.id}`}
                              label={isKeep ? t('Keep') : t('Keep this')}
                              checked={isKeep}
                              onChange={() =>
                                setKeepByGroup((prev) => ({ ...prev, [group.key]: item.id }))
                              }
                            />
                            <div className="small text-muted mt-1 text-truncate" title={item.filename || ''}>
                              {item.filename || `#${item.id}`}
                            </div>
                            <div className="small text-muted">
                              {item.width && item.height ? `${item.width}×${item.height} · ` : ''}
                              {formatBytes(item.bytes)}
                            </div>
                            <div className="small text-muted">{item.source_label}</div>
                          </Card.Body>
                        </Card>
                      </Col>
                    );
                  })}
                </Row>
              </Card.Body>
            </Card>
          );
        })
      )}

      <Modal show={!!pendingGroup} onHide={() => setPendingGroup(null)} centered>
        <Modal.Header closeButton>
          <Modal.Title>{t('Delete duplicates?')}</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {pendingGroup && (
            <>
              <p className="mb-2">
                {t('Keep 1 item and soft-delete the other {{n}}. Originals stay on storage and can be recovered.', {
                  n: Math.max(0, pendingGroup.items.length - 1),
                })}
              </p>
            </>
          )}
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setPendingGroup(null)} disabled={deleting}>
            {t('Cancel')}
          </Button>
          <Button
            variant="danger"
            onClick={() => pendingGroup && deleteOthers(pendingGroup)}
            disabled={deleting}
          >
            {deleting ? <Spinner size="sm" animation="border" /> : t('Delete')}
          </Button>
        </Modal.Footer>
      </Modal>
    </Container>
  );
};

export default MediaDuplicatesPage;

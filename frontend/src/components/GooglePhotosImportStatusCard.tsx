import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Badge, Button, Card, ListGroup, Spinner } from 'react-bootstrap';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../services/api';
import { PickerSessionRow } from '../types/api';
import { formatDateTime } from '../utils/format';
import {
  describeImportSessionStatus,
  isActiveImportSessionStatus,
} from '../utils/importSessionStatus';

interface GooglePhotosImportStatusCardProps {
  // セッション作成直後などに親から再読込を指示するためのトークン
  reloadToken?: number;
}

const POLL_INTERVAL_MS = 10000;
const MAX_ROWS = 5;

// Google フォト取り込みのステータスカード。
// Local Import の「Import Status」と対になる表示で、直近のセッションの
// 進行状況（選択待ち → 取り込み中 → 完了）を一覧する。
// 進行中のセッションがある間はポーリングし、Google 側で選択が確定した
// セッションは自動で取り込みを開始する（サーバー側の定期タスクの補完）。
const GooglePhotosImportStatusCard: React.FC<GooglePhotosImportStatusCardProps> = ({
  reloadToken,
}) => {
  const { t } = useTranslation();
  const [sessions, setSessions] = useState<PickerSessionRow[] | null>(null);
  const [loading, setLoading] = useState(false);
  // 取り込み開始要求の二重送信防止（sessionId の集合）
  const startRequestedRef = useRef<Set<string>>(new Set());

  const load = useCallback(async (): Promise<PickerSessionRow[]> => {
    try {
      const data = await apiClient.getPickerSessions({ page: 1, pageSize: 20 });
      const googleSessions = (data.sessions || [])
        .filter((s) => !s.isLocalImport)
        .slice(0, MAX_ROWS);
      setSessions(googleSessions);
      return googleSessions;
    } catch {
      return sessions ?? [];
    }
  }, [sessions]);

  // 進行中セッションの状態を進める:
  // ステータス照会（サーバーが Google をポーリングして DB を更新）→
  // 選択確定済みなら取り込み開始。
  const advanceActiveSessions = useCallback(async (rows: PickerSessionRow[]) => {
    const active = rows.filter((r) => r.sessionId && isActiveImportSessionStatus(r.status));
    for (const row of active.slice(0, 3)) {
      try {
        const status = await apiClient.getPickerSessionStatus(row.sessionId);
        const waiting = status.status === 'pending' || status.status === 'ready';
        if (status.mediaItemsSet && waiting && !startRequestedRef.current.has(row.sessionId)) {
          startRequestedRef.current.add(row.sessionId);
          await apiClient.startPickerSessionImport(row.sessionId);
        }
      } catch {
        // 単発の失敗は次のポーリングで再試行する
      }
    }
    return active.length > 0;
  }, []);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const tick = async (showSpinner: boolean) => {
      if (showSpinner) setLoading(true);
      const rows = await load();
      if (cancelled) return;
      if (showSpinner) setLoading(false);
      const hasActive = await advanceActiveSessions(rows);
      if (cancelled) return;
      if (hasActive) {
        // 取り込み開始/進行を反映するため、進行中の間だけポーリングを続ける
        timer = setTimeout(() => tick(false), POLL_INTERVAL_MS);
      }
    };

    tick(true);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reloadToken]);

  const countsSummary = (row: PickerSessionRow): string | null => {
    const counts = row.counts || {};
    const total = Object.values(counts).reduce((sum, v) => sum + v, 0);
    if (total === 0) {
      if (row.selectedCount > 0) {
        return t('{{count}} item(s) selected', { count: row.selectedCount });
      }
      return null;
    }
    const done = (counts.imported || 0) + (counts.dup || 0) + (counts.skipped || 0);
    const failed = counts.failed || 0;
    const parts = [t('{{done}} of {{total}} processed', { done, total })];
    if (failed > 0) parts.push(t('{{count}} failed', { count: failed }));
    return parts.join(' / ');
  };

  return (
    <Card className="mb-4" data-testid="google-import-status-card">
      <Card.Header className="fw-semibold d-flex justify-content-between align-items-center">
        <span>{t('Import Status')}</span>
        <Button
          variant="outline-secondary"
          size="sm"
          onClick={() => load()}
          data-testid="google-import-status-refresh"
        >
          <i className="fa-solid fa-rotate-right" />
        </Button>
      </Card.Header>
      {sessions === null ? (
        <Card.Body className="text-center py-4">
          {loading ? <Spinner animation="border" size="sm" /> : null}
        </Card.Body>
      ) : sessions.length === 0 ? (
        <Card.Body className="text-muted small" data-testid="google-import-status-empty">
          {t('No Google Photos imports yet.')}
        </Card.Body>
      ) : (
        <ListGroup variant="flush" data-testid="google-import-status-list">
          {sessions.map((row) => {
            const presentation = describeImportSessionStatus(row.status);
            const summary = countsSummary(row);
            return (
              <ListGroup.Item
                key={row.id}
                className="d-flex flex-wrap align-items-center gap-2 py-2"
                data-testid="google-import-status-row"
              >
                <div className="flex-grow-1 me-2" style={{ minWidth: 0 }}>
                  <div className="small text-truncate">
                    <i className="fa-brands fa-google me-1 text-muted" />
                    {row.accountEmail || t('Google account')}
                  </div>
                  <div className="text-muted small">
                    {formatDateTime(row.createdAt)}
                    {summary && <span className="ms-2">{summary}</span>}
                  </div>
                </div>
                <Badge bg={presentation.variant} data-testid="google-import-status-badge">
                  {presentation.active && (
                    <Spinner animation="border" size="sm" className="me-1" style={{ width: 10, height: 10, borderWidth: 1 }} />
                  )}
                  {t(presentation.labelKey)}
                </Badge>
                <Link
                  to={`/sessions/${encodeURIComponent(row.sessionId)}`}
                  className="small text-decoration-none"
                >
                  {t('Details')}
                </Link>
              </ListGroup.Item>
            );
          })}
        </ListGroup>
      )}
      <Card.Footer className="bg-white small text-muted">
        {t('After selecting photos in Google Photos, the import starts automatically (within about a minute).')}{' '}
        <Link to="/sessions" className="text-decoration-none">{t('View all sessions')}</Link>
      </Card.Footer>
    </Card>
  );
};

export default GooglePhotosImportStatusCard;

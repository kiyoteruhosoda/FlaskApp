import React, { useCallback, useEffect, useState } from 'react';
import { Badge, Dropdown, Spinner } from 'react-bootstrap';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../services/api';
import { PickerSessionRow } from '../types/api';
import {
  describeImportSessionStatus,
  isActiveImportSessionStatus,
} from '../utils/importSessionStatus';

const POLL_INTERVAL_MS = 30000;
const MAX_ITEMS = 8;

// 現在実行中／直近の取り込み作業を知らせるベルアイコン。
// 「いま何が動いているのか」「終わったのか」をどの画面からでも
// 確認できるようにし、各作業の詳細ページへのリンクを提供する。
const ImportActivityBell: React.FC = () => {
  const { t } = useTranslation();
  const [items, setItems] = useState<PickerSessionRow[]>([]);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await apiClient.getPickerSessions({ page: 1, pageSize: MAX_ITEMS });
      setItems(data.sessions || []);
      setLoaded(true);
    } catch {
      // 通知は補助機能なので失敗しても静かに次のポーリングへ
    }
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [load]);

  const activeCount = items.filter((s) => isActiveImportSessionStatus(s.status)).length;

  const itemLabel = (row: PickerSessionRow): string => {
    if (row.isLocalImport) return t('Local import');
    return row.accountEmail
      ? `${t('Google Photos import')} (${row.accountEmail})`
      : t('Google Photos import');
  };

  const relativeTime = (iso: string | null): string => {
    if (!iso) return '—';
    const diffMs = Date.now() - new Date(iso).getTime();
    const minutes = Math.floor(diffMs / 60000);
    if (minutes < 1) return t('just now');
    if (minutes < 60) return t('{{count}} min ago', { count: minutes });
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return t('{{count}} hr ago', { count: hours });
    return new Date(iso).toLocaleDateString();
  };

  return (
    <Dropdown align="end" onToggle={(nextShow) => { if (nextShow) load(); }}>
      <Dropdown.Toggle
        variant="link"
        className="text-secondary text-decoration-none px-2 no-caret"
        bsPrefix="btn"
        aria-label={t('Import activity')}
        data-testid="import-activity-bell"
      >
        <span className="position-relative d-inline-flex">
          <i className="fa-solid fa-bell fs-5" />
          {activeCount > 0 && (
            <Badge
              pill
              bg="danger"
              className="position-absolute top-0 start-100 translate-middle"
              style={{ fontSize: '0.65rem' }}
              data-testid="import-activity-count"
            >
              {activeCount}
            </Badge>
          )}
        </span>
      </Dropdown.Toggle>
      <Dropdown.Menu style={{ minWidth: 320, maxWidth: 380 }} data-testid="import-activity-menu">
        <Dropdown.Header>
          {activeCount > 0
            ? t('{{count}} task(s) in progress', { count: activeCount })
            : t('No tasks in progress')}
        </Dropdown.Header>
        {!loaded && (
          <div className="text-center py-3"><Spinner animation="border" size="sm" /></div>
        )}
        {loaded && items.length === 0 && (
          <div className="text-muted small px-3 py-2">{t('No recent import activity.')}</div>
        )}
        {items.map((row) => {
          const presentation = describeImportSessionStatus(row.status);
          return (
            <Dropdown.Item
              key={row.id}
              as={Link}
              to={`/sessions/${encodeURIComponent(row.sessionId)}`}
              className="py-2"
              data-testid="import-activity-item"
            >
              <div className="d-flex align-items-center gap-2">
                <i
                  className={`fa-fw ${row.isLocalImport ? 'fa-solid fa-desktop' : 'fa-brands fa-google'} text-muted`}
                />
                <div className="flex-grow-1" style={{ minWidth: 0 }}>
                  <div className="small text-truncate">{itemLabel(row)}</div>
                  <div className="text-muted" style={{ fontSize: '0.75rem' }}>
                    {relativeTime(row.createdAt)}
                  </div>
                </div>
                <Badge bg={presentation.variant} style={{ fontSize: '0.65rem' }}>
                  {t(presentation.labelKey)}
                </Badge>
              </div>
            </Dropdown.Item>
          );
        })}
        <Dropdown.Divider />
        <Dropdown.Item as={Link} to="/sessions" className="small text-center">
          {t('View all sessions')}
        </Dropdown.Item>
      </Dropdown.Menu>
    </Dropdown>
  );
};

export default ImportActivityBell;

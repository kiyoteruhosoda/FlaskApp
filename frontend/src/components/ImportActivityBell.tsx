import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Badge, Dropdown, Spinner } from 'react-bootstrap';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../services/api';
import { PickerSessionRow } from '../types/api';
import { formatDate } from '../utils/format';
import {
  describeImportSessionStatus,
  isActiveImportSessionStatus,
} from '../utils/importSessionStatus';

const POLL_INTERVAL_MS = 30000;
const MAX_ITEMS = 8;
// 既読フェーズを永続化するキー。取り込み「開始」と「終了」の 2 段階だけを
// 通知対象とするため、セッションごとに 'active'（進行中）/'done'（完了・失敗）の
// フェーズを保存し、現在のフェーズと違う＝未読として扱う。
const SEEN_STORAGE_KEY = 'importActivitySeenPhase.v1';

type SessionPhase = 'active' | 'done';

const phaseOf = (status: string | null | undefined): SessionPhase =>
  isActiveImportSessionStatus(status) ? 'active' : 'done';

const keyOf = (row: PickerSessionRow): string => row.sessionId || String(row.id);

const loadSeenMap = (): Record<string, SessionPhase> => {
  try {
    const raw = localStorage.getItem(SEEN_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
};

const saveSeenMap = (map: Record<string, SessionPhase>): void => {
  try {
    localStorage.setItem(SEEN_STORAGE_KEY, JSON.stringify(map));
  } catch {
    /* localStorage が使えない環境では通知の永続化を諦める */
  }
};

// 現在実行中／直近の取り込み作業を知らせるベルアイコン。
// 「いま何が動いているのか」「終わったのか」をどの画面からでも
// 確認できるようにし、各作業の詳細ページへのリンクを提供する。
//
// バッジは「未読の通知件数」を表す。取り込みが始まると（開始通知）、
// 終わると（終了通知：正常・異常とも）バッジが立ち、ベルを開いて中身を
// 見るまで消えない。完了と同時に自動で消えてしまい見逃す問題を防ぐ。
const ImportActivityBell: React.FC = () => {
  const { t } = useTranslation();
  const [items, setItems] = useState<PickerSessionRow[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [unseenIds, setUnseenIds] = useState<Set<string>>(new Set());
  const seenRef = useRef<Record<string, SessionPhase>>(loadSeenMap());
  // 初回ロード時は既存セッションを一括で既読扱いにし、いきなり大量の
  // 未読バッジが出ないようにする（以後の変化だけを通知する）。
  const seededRef = useRef<boolean>(Boolean(localStorage.getItem(SEEN_STORAGE_KEY)));

  const load = useCallback(async () => {
    try {
      const data = await apiClient.getPickerSessions({ page: 1, pageSize: MAX_ITEMS });
      const rows = data.sessions || [];
      setItems(rows);

      if (!seededRef.current) {
        const seeded: Record<string, SessionPhase> = {};
        rows.forEach((row) => { seeded[keyOf(row)] = phaseOf(row.status); });
        seenRef.current = seeded;
        saveSeenMap(seeded);
        seededRef.current = true;
        setUnseenIds(new Set());
      } else {
        const seen = seenRef.current;
        const unseen = new Set<string>();
        rows.forEach((row) => {
          if (seen[keyOf(row)] !== phaseOf(row.status)) unseen.add(keyOf(row));
        });
        setUnseenIds(unseen);
      }
      setLoaded(true);
    } catch {
      // 通知は補助機能なので失敗しても静かに次のポーリングへ
    }
  }, []);

  // ベルを開いた（＝見た）ら、現在表示中のセッションを既読フェーズとして保存し、
  // 未読バッジを消す。次に開始／終了フェーズへ変化したら再びバッジが立つ。
  const markSeen = useCallback(() => {
    const seen = { ...seenRef.current };
    items.forEach((row) => { seen[keyOf(row)] = phaseOf(row.status); });
    seenRef.current = seen;
    saveSeenMap(seen);
    setUnseenIds(new Set());
  }, [items]);

  useEffect(() => {
    load();
    const timer = setInterval(load, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [load]);

  const activeCount = items.filter((s) => isActiveImportSessionStatus(s.status)).length;
  const unseenCount = unseenIds.size;

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
    return formatDate(iso);
  };

  return (
    <Dropdown align="end" onToggle={(nextShow) => { if (nextShow) { load(); markSeen(); } }}>
      <Dropdown.Toggle
        variant="link"
        className="text-secondary text-decoration-none px-2 no-caret"
        bsPrefix="btn"
        aria-label={t('Import activity')}
        data-testid="import-activity-bell"
      >
        <span className="position-relative d-inline-flex">
          <i className="fa-solid fa-bell fs-5" />
          {unseenCount > 0 && (
            <Badge
              pill
              bg="danger"
              className="position-absolute top-0 start-100 translate-middle"
              style={{ fontSize: '0.65rem' }}
              data-testid="import-activity-count"
            >
              {unseenCount}
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

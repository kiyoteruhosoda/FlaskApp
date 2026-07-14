// 表示用の共通フォーマットユーティリティ

// 画面表示に用いるタイムゾーン（IANA 名）。ユーザーの Profile 設定に由来する。
// 未設定（空/undefined）のときはブラウザのタイムゾーンにフォールバックする。
// バックエンド/DB は常に UTC で保持・送出し、現地時刻への変換はこの表示層のみで行う。
// 注意: System Logs（監査・時系列突合用途）は UTC のまま表示するため、
// これらの整形関数を経由させない。
const TIMEZONE_STORAGE_KEY = 'display_timezone';

function readStoredTimeZone(): string | undefined {
  try {
    const v = localStorage.getItem(TIMEZONE_STORAGE_KEY);
    return v && v.trim() ? v : undefined;
  } catch {
    return undefined;
  }
}

// リロード直後でも設定を反映できるよう localStorage から初期化する。
let activeTimeZone: string | undefined = readStoredTimeZone();

// 表示タイムゾーンを設定する（空/undefined でブラウザ検出へ戻す）。localStorage にも永続化する。
export function setActiveTimeZone(tz: string | null | undefined): void {
  const normalized = tz && tz.trim() ? tz.trim() : undefined;
  activeTimeZone = normalized;
  try {
    if (normalized) {
      localStorage.setItem(TIMEZONE_STORAGE_KEY, normalized);
    } else {
      localStorage.removeItem(TIMEZONE_STORAGE_KEY);
    }
  } catch {
    /* localStorage 不可の環境では無視する */
  }
}

// 現在有効なタイムゾーン（未設定時はブラウザ検出値）を返す。
export function getActiveTimeZone(): string {
  return activeTimeZone ?? Intl.DateTimeFormat().resolvedOptions().timeZone;
}

// toLocaleString 系に渡すオプションへ現在の表示タイムゾーンを合成する。
// activeTimeZone が undefined の場合は timeZone を指定せずブラウザ既定を使う。
function withTimeZone(
  options?: Intl.DateTimeFormatOptions,
): Intl.DateTimeFormatOptions | undefined {
  if (!activeTimeZone) return options;
  return { ...(options ?? {}), timeZone: activeTimeZone };
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString(undefined, withTimeZone());
}

// 日付のみ（時刻なし）を現地タイムゾーンで整形する。
export function formatDate(value: string | null | undefined): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString(undefined, withTimeZone());
}

// 時刻のみ（日付なし）を現地タイムゾーンで整形する。
export function formatTime(value: string | null | undefined): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleTimeString(undefined, withTimeZone());
}

// ミリ秒まで表示する日時フォーマット（ログ解析用。同一秒内の順序を判別できる）。
// ログ（System Logs）は監査・時系列突合の用途のため、ユーザーの表示タイムゾーン設定に
// 依存せず常に UTC で表示する（画面の列見出しも "Time (UTC)"）。他の整形関数と異なり
// activeTimeZone を適用しない点に注意。
export function formatDateTimeWithMs(value: string | null | undefined): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  // fractionalSecondDigits は実行環境（モダンブラウザ）では有効だが、TS の
  // lib バージョンによっては型定義に無いため交差型で明示的に許可する。
  const options: Intl.DateTimeFormatOptions & {
    fractionalSecondDigits?: 1 | 2 | 3;
  } = {
    timeZone: 'UTC',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    fractionalSecondDigits: 3,
  };
  return d.toLocaleString(undefined, options);
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '—';
  if (ms < 1000) return `${ms} ms`;
  const sec = Math.floor(ms / 1000);
  if (sec < 60) return `${sec}s`;
  const min = Math.floor(sec / 60);
  const rem = sec % 60;
  if (min < 60) return `${min}m ${rem}s`;
  const hr = Math.floor(min / 60);
  return `${hr}h ${min % 60}m`;
}

// ジョブ状態 → Bootstrap バッジ色
export function jobStatusVariant(status: string): string {
  switch (status) {
    case 'success':
      return 'success';
    case 'running':
      return 'primary';
    case 'queued':
      return 'secondary';
    case 'partial':
      return 'warning';
    case 'failed':
      return 'danger';
    case 'canceled':
      return 'dark';
    default:
      return 'light';
  }
}

// セッション状態 → Bootstrap バッジ色
export function sessionStatusVariant(status: string): string {
  switch (status) {
    case 'imported':
    case 'ready':
    case 'completed':
      return 'success';
    case 'processing':
    case 'importing':
    case 'expanding':
      return 'primary';
    case 'pending':
    case 'enqueued':
      return 'secondary';
    case 'error':
    case 'failed':
      return 'danger';
    case 'canceled':
      return 'dark';
    default:
      return 'light';
  }
}

// 明るい背景色のバッジは既定の白文字だと読めない（白地に白）ため、
// 濃い文字色を指定すべき variant を返す。react-bootstrap の
// <Badge bg={variant} text={badgeTextColor(variant)}> で使う。
export function badgeTextColor(variant: string): 'dark' | undefined {
  return ['light', 'warning', 'info'].includes(variant) ? 'dark' : undefined;
}

// counts オブジェクトを "imported:3 failed:1" のような文字列に
export function formatCounts(counts: Record<string, number> | undefined): string {
  if (!counts) return '';
  return Object.entries(counts)
    .filter(([, v]) => v)
    .map(([k, v]) => `${k}:${v}`)
    .join('  ');
}

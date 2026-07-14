// 表示用の共通フォーマットユーティリティ

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString();
}

// ミリ秒まで表示する日時フォーマット（ログ解析用。同一秒内の順序を判別できる）。
export function formatDateTimeWithMs(value: string | null | undefined): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  // fractionalSecondDigits は実行環境（モダンブラウザ）では有効だが、TS の
  // lib バージョンによっては型定義に無いため交差型で明示的に許可する。
  const options: Intl.DateTimeFormatOptions & {
    fractionalSecondDigits?: 1 | 2 | 3;
  } = {
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

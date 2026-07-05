// 取り込みセッション（Google フォト / ローカル）のステータス表示語彙。
// バックエンドの PickerSession.status をユーザー向けのラベル・色・
// 「進行中かどうか」に対応付ける単一の出所。

export interface ImportSessionStatusPresentation {
  // i18n の翻訳キー（英語の原文）
  labelKey: string;
  // react-bootstrap Badge の variant
  variant: string;
  // 進行中（＝まだ完了していない）作業として扱うか
  active: boolean;
}

const STATUS_PRESENTATIONS: Record<string, ImportSessionStatusPresentation> = {
  pending: { labelKey: 'Waiting for photo selection', variant: 'info', active: true },
  ready: { labelKey: 'Selected, waiting to import', variant: 'info', active: true },
  enqueued: { labelKey: 'Importing', variant: 'primary', active: true },
  processing: { labelKey: 'Importing', variant: 'primary', active: true },
  importing: { labelKey: 'Importing', variant: 'primary', active: true },
  expanding: { labelKey: 'Preparing files', variant: 'primary', active: true },
  imported: { labelKey: 'Completed', variant: 'success', active: false },
  error: { labelKey: 'Error', variant: 'danger', active: false },
  failed: { labelKey: 'Error', variant: 'danger', active: false },
  expired: { labelKey: 'Expired (no selection)', variant: 'secondary', active: false },
  canceled: { labelKey: 'Canceled', variant: 'secondary', active: false },
};

export const describeImportSessionStatus = (
  status: string | null | undefined,
): ImportSessionStatusPresentation => {
  if (status && STATUS_PRESENTATIONS[status]) return STATUS_PRESENTATIONS[status];
  return { labelKey: status || 'Unknown', variant: 'secondary', active: false };
};

export const isActiveImportSessionStatus = (status: string | null | undefined): boolean =>
  describeImportSessionStatus(status).active;

// 基本的な型定義
export interface User {
  id: string;
  username: string;
  email: string;
  roles: Role[];
  permissions: string[];
  created_at: string;
  updated_at: string;
}

export interface Role {
  id: string;
  name: string;
  permissions: Permission[];
}

export interface Permission {
  id: string;
  scope: string;
  name: string;
  description?: string;
}

// 認証関連
export interface LoginRequest {
  email: string;
  password: string;
  token?: string;
  scope?: string[];
  active_role_id?: number;
  next_url?: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type?: string;
  requires_role_selection?: boolean;
  redirect_url?: string;
  scope?: string;
  available_scopes?: string[];
}

export interface RegisterRequest {
  username: string;
  email: string;
  password: string;
  password_confirm: string;
  totp_secret?: string;
  totp_code?: string;
}

// メディア関連
export interface Media {
  id: string;
  filename: string;
  file_path: string;
  file_size: number;
  mime_type: string;
  media_type: 'photo' | 'video';
  width?: number;
  height?: number;
  duration?: number;
  created_at: string;
  updated_at: string;
  thumbnail_sizes: number[];
}

export interface MediaSession {
  id: string;
  name: string;
  description?: string;
  session_date: string;
  media_count: number;
  created_at: string;
  updated_at: string;
}

export interface Album {
  id: string;
  name: string;
  description?: string;
  cover_media_id?: string;
  media_count: number;
  created_at: string;
  updated_at: string;
}

// API レスポンス型
export interface ApiResponse<T = any> {
  success: boolean;
  data?: T;
  message?: string;
  errors?: Record<string, string[]>;
}

export interface PaginatedResponse<T> extends ApiResponse<T[]> {
  pagination: {
    page: number;
    pageSize: number;
    total: number;
    totalPages: number;
    hasNext: boolean;
    hasPrev: boolean;
    nextCursor?: string;
    prevCursor?: string;
  };
}

// 設定関連
export interface SystemSettings {
  [key: string]: any;
}

export interface GoogleAccount {
  id: string;
  email: string;
  name: string;
  is_active: boolean;
  last_sync: string;
  created_at: string;
}

// ===== Google アカウント連携（/api/google/*） =====
export interface LinkedGoogleAccount {
  id: number;
  email: string;
  status: 'active' | 'disabled' | string;
  scopes: string[];
  last_synced_at: string | null;
  has_token: boolean;
}

export interface GoogleOAuthStartResponse {
  auth_url: string;
  server_time?: string;
}

// POST /api/picker/session のレスポンス
export interface PickerSessionCreateResponse {
  pickerSessionId: number;
  sessionId: string | null;
  pickerUri: string | null;
  expireTime?: string | null;
  pollingConfig?: Record<string, unknown> | null;
  pickingConfig?: Record<string, unknown> | null;
  mediaItemsSet?: boolean | null;
}

// フォーム関連
export interface FormFieldError {
  field: string;
  message: string;
}

// Celeryタスク関連
export interface TaskStatus {
  task_id: string;
  status: 'PENDING' | 'STARTED' | 'SUCCESS' | 'FAILURE' | 'RETRY' | 'REVOKED';
  result?: any;
  error?: string;
  progress?: number;
}
// ===== 同期・変換ジョブ履歴 (/api/sync/jobs) =====
export type JobStatus =
  | 'queued'
  | 'running'
  | 'success'
  | 'partial'
  | 'failed'
  | 'canceled';

export type JobTargetCategory =
  | 'local_import'
  | 'picker_import'
  | 'transcode'
  | 'thumbnail'
  | 'google_photos'
  | 'other';

export interface SyncJob {
  id: number;
  target: string;
  targetCategory: JobTargetCategory;
  taskName: string | null;
  queueName: string | null;
  trigger: string | null;
  status: JobStatus;
  accountId: number | null;
  sessionId: number | null;
  celeryTaskId: number | null;
  startedAt: string | null;
  finishedAt: string | null;
  durationMs: number | null;
  statsSummary: Record<string, number>;
  errorMessage: string | null;
  retryable: boolean;
}

export interface SyncJobDetail extends SyncJob {
  stats: Record<string, any>;
  args: Record<string, any>;
  celeryTask?: {
    taskName: string;
    status: string;
    errorMessage: string | null;
    startedAt: string | null;
    finishedAt: string | null;
  };
}

export interface Pagination {
  currentPage: number;
  pageSize: number;
  totalCount: number;
  totalPages: number;
  hasNext: boolean;
  hasPrev: boolean;
}

export interface SyncJobListResponse {
  jobs: SyncJob[];
  pagination: Pagination;
  filter: {
    status: string | null;
    target: string | null;
    since: string | null;
    until: string | null;
  };
  server_time: string;
}

export interface SyncJobDetailResponse {
  job: SyncJobDetail;
  server_time: string;
}

export interface SyncJobsQuery {
  page?: number;
  pageSize?: number;
  status?: JobStatus | '';
  target?: JobTargetCategory | '';
  since?: string;
  until?: string;
}

// ===== Picker セッション一覧 (/api/picker/sessions) =====
export interface PickerSessionRow {
  id: number;
  sessionId: string;
  accountId: number | null;
  status: string;
  selectedCount: number;
  createdAt: string | null;
  lastProgressAt: string | null;
  counts: Record<string, number>;
  accountEmail: string | null;
  isLocalImport: boolean;
}

export interface PickerSessionListResponse {
  sessions: PickerSessionRow[];
  pagination: {
    hasNext: boolean;
    hasPrev: boolean;
    nextCursor: string | null;
    prevCursor: string | null;
    currentPage: number | null;
    totalPages: number | null;
    totalCount: number | null;
  };
  server_time: string;
}

// ===== 写真管理 (media / albums / tags) =====
export interface MediaTag {
  id: number;
  name: string;
  attr: string | null;
}

export interface PhotoItem {
  id: number;
  filename: string | null;
  shot_at: string | null;
  mime_type: string | null;
  width: number | null;
  height: number | null;
  is_video: number;
  has_playback: number;
  bytes: number | null;
  source_type: string | null;
  source_label: string | null;
  account_id: number | null;
  account_email: string | null;
  camera_make: string | null;
  camera_model: string | null;
  tags: MediaTag[];
}

export interface CursorListResponse<T> {
  items: T[];
  hasNext?: boolean;
  hasPrev?: boolean;
  nextCursor?: string | null;
  prevCursor?: string | null;
  server_time?: string;
}

export interface AlbumSummary {
  id: number;
  title: string;
  description: string | null;
  visibility: string | null;
  coverImageId: number | null;
  coverMediaId: number | null;
  mediaCount: number;
  createdAt: string | null;
  updatedAt: string | null;
  lastModified: string | null;
  displayOrder: number | null;
}

export interface AlbumMediaItem {
  id: number;
  filename: string | null;
  shotAt: string | null;
  thumbnailUrl: string;
  fullUrl: string;
  sortIndex: number | null;
  tags: MediaTag[];
}

export interface AlbumDetail extends AlbumSummary {
  media: AlbumMediaItem[];
  mediaIds: number[];
}

// ===== 管理 API =====

export interface AdminRoleRef {
  id: number;
  name: string;
}

export interface AdminUser {
  id: number;
  email: string;
  username: string | null;
  isActive: boolean;
  hasTOTP: boolean;
  createdAt: string | null;
  roles: AdminRoleRef[];
}

export interface AdminRole {
  id: number;
  name: string;
  permissions: string[];
  isDefault?: boolean;
}

// ===== 管理 API — ロール CRUD =====

export interface AdminRoleDetail {
  id: number;
  name: string;
  permissions: Array<{ id: number; code: string }>;
  userCount: number;
  isDefault?: boolean;
}

// ===== 管理 API — グループ =====

export interface AdminGroup {
  id: number;
  name: string;
  description: string | null;
  parentId: number | null;
  parentName: string | null;
  memberCount: number;
  childCount: number;
}

export interface AdminGroupDetail extends AdminGroup {
  members: Array<{ id: number; email: string; username: string | null }>;
}

// ===== 管理 API — 権限 =====

export interface AdminPermission {
  id: number;
  code: string;
  detail: string | null;
  roleCount: number;
}

// ===== 管理 API — サービスアカウント =====

export interface AdminServiceAccount {
  id: number;
  name: string;
  description: string | null;
  scopes: string[];
  isActive: boolean;
  createdAt: string | null;
  updatedAt: string | null;
}

// ===== 管理 API — ダッシュボード =====

export interface DashboardStats {
  users: { total: number; active: number };
  roles: number;
  groups: number;
  serviceAccounts: number;
  media?: { total: number; photos: number; videos: number };
  albums?: number;
  tags?: number;
  recentJobs: Array<{ id: number; target: string; status: string; startedAt: string | null }>;
}

// ===== パスキー =====

export interface PasskeyItem {
  id: number;
  name: string | null;
  createdAt: string | null;
  lastUsedAt: string | null;
  transports: string[];
}

// ===== プロフィール・2FA・登録 =====

export interface ProfileUpdateRequest {
  email?: string;
  username?: string;
  password?: string;
}

export interface ProfileUpdateResponse {
  updated: boolean;
  user: {
    id: number;
    email: string;
    username: string | null;
  };
}

export interface TOTPStatusResponse {
  enabled: boolean;
}

export interface TOTPSetupResponse {
  secret: string;
  otpauth_uri: string;
  qr_data_uri: string;
}

export interface RegisterUserRequest {
  email: string;
  password: string;
  username?: string;
}

export interface RegisterUserResponse {
  user: {
    id: number;
    email: string;
    username: string | null;
  };
  access_token: string;
  refresh_token: string;
  token_type: string;
}

// ===== セッション詳細・ログ =====

export interface PickerSessionStatus {
  id: number;
  sessionId: string;
  status: string;
  accountId: number | null;
  accountEmail: string | null;
  selectedCount: number | null;
  counts: Record<string, number>;
  createdAt: string | null;
  lastProgressAt: string | null;
  isLocalImport: boolean;
  stats: Record<string, any> | null;
}

export interface PickerSelectionItem {
  id: number;
  sessionDbId: number;
  googleMediaId: string | null;
  filename: string | null;
  status: string;
  attempts: number;
  error: string | null;
  localFilePath: string | null;
  enqueuedAt: string | null;
  startedAt: string | null;
  finishedAt: string | null;
}

export interface SessionLogEntry {
  id: number;
  level: string;
  message: string;
  timestamp: string;
  fileTaskId: string | null;
  progressStep: number | null;
}

export interface SelectionErrorPayload {
  session: { id: number; sessionId: string; status: string; accountId: number | null };
  selection: PickerSelectionItem;
  logs: SessionLogEntry[];
}

export interface PickerSessionLogsResponse {
  logs: SessionLogEntry[];
  hasNext: boolean;
  nextCursor: number | null;
  fileTaskIds: string[];
}

export interface PickerSessionSelectionsResponse {
  selections: PickerSelectionItem[];
  pagination: {
    hasNext: boolean;
    totalCount: number | null;
  };
}

// ===== ローカルインポート設定 =====

export interface DirectoryInfo {
  key: string;
  config_key: string;
  label: string;
  path: string | null;
  absolute: string | null;
  realpath: string | null;
  exists: boolean;
  source: string;
}

export interface LocalImportStatusResponse {
  config: {
    import_dir: string | null;
    originals_dir: string | null;
    import_dir_absolute: string | null;
    import_dir_realpath: string | null;
    import_dir_exists: boolean;
    originals_dir_exists: boolean;
  };
  status: {
    pending_files: number;
    ready: boolean;
  };
  directories: DirectoryInfo[];
  defaults: { duplicateRegeneration: string };
  server_time: string;
}

export interface LocalImportUploadResponse {
  success: boolean;
  saved: Array<{ filename: string; size: number }>;
  skipped: Array<{ filename: string; reason: string }>;
  server_time: string;
}

// ===== バージョン情報 =====

export interface VersionResponse {
  ok: boolean;
  version: string;
  details?: Record<string, unknown>;
}

// ===== アプリケーション設定 (/admin/config) =====

export type ConfigFieldType = 'string' | 'integer' | 'float' | 'boolean' | 'list';

export interface ConfigField {
  key: string;
  label: string;
  data_type: ConfigFieldType;
  required: boolean;
  description: string;
  current_json: string;
  default_json: string;
  form_value: string;
  choices: Array<[string, string]>;
  multiline: boolean;
  using_default: boolean;
  allow_empty: boolean;
  allow_null: boolean;
  editable: boolean;
  default_hint: string | null;
  // 入力欄の直後に表示する固定サフィックス（値の一部が固定であることを明示）
  input_suffix?: string | null;
  search_text: string;
  section: string;
  section_label: string;
  anchor_id: string;
}

export interface ConfigSection {
  identifier: string;
  label: string;
  description: string | null;
  fields: ConfigField[];
  anchor_id: string;
  search_text: string;
}

export interface SigningSetting {
  mode: string;
  kid: string | null;
  group_code: string | null;
}

export interface SigningCertificate {
  kid: string | null;
  issuedAt: string | null;
  expiresAt: string | null;
  algorithm: string | null;
  subject: string | null;
}

export interface SigningGroup {
  groupCode: string;
  groupLabel: string;
  latestCertificate: SigningCertificate | null;
}

export interface ConfigResponse {
  application_sections: ConfigSection[];
  application_fields: ConfigField[];
  cors_fields: ConfigField[];
  cors_effective_origins: string[];
  signing_setting: SigningSetting | null;
  signingGroups: SigningGroup[];
  builtin_signing_secret: string | null;
  timestamps: {
    application_config_updated_at: string | null;
    cors_config_updated_at: string | null;
    signing_config_updated_at: string | null;
  };
  descriptions: {
    application_config_description: string | null;
    cors_config_description: string | null;
  };
  warnings?: string[];
  updated?: boolean;
  status: string;
}

// 重複検出（人手レビュー）
export interface DuplicateMember {
  id: number;
  filename: string | null;
  thumbnail_url: string;
  width: number | null;
  height: number | null;
  bytes: number | null;
  is_video: number;
  source_type: string;
  source_label: string;
  shot_at: string | null;
  imported_at: string | null;
}

export interface DuplicateGroup {
  key: string;
  match_type: 'exact' | 'similar';
  count: number;
  items: DuplicateMember[];
}

export interface DuplicateGroupsResponse {
  groups: DuplicateGroup[];
  group_count: number;
}

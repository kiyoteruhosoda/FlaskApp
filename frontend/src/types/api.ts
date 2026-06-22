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
}

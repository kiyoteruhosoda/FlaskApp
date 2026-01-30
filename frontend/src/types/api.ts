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
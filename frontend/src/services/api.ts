import axios, { AxiosInstance, AxiosRequestConfig, AxiosResponse } from 'axios';
import {
  LoginRequest,
  LoginResponse,
  RegisterRequest,
  User,
  Media,
  MediaSession,
  Album,
  ApiResponse,
  PaginatedResponse,
  SystemSettings,
  GoogleAccount,
  TaskStatus,
  SyncJobListResponse,
  SyncJobDetailResponse,
  SyncJobsQuery,
  PickerSessionListResponse,
  PhotoItem,
  AlbumSummary,
  AlbumDetail,
  MediaTag,
  CursorListResponse,
  AdminUser,
  AdminRole,
  AdminRoleDetail,
  AdminGroup,
  AdminGroupDetail,
  AdminPermission,
  AdminServiceAccount,
  DashboardStats,
  PasskeyItem,
  ProfileUpdateRequest,
  ProfileUpdateResponse,
  TOTPStatusResponse,
  TOTPSetupResponse,
  RegisterUserRequest,
  RegisterUserResponse,
  PickerSessionStatus,
  PickerSessionLogsResponse,
  PickerSessionSelectionsResponse,
  SelectionErrorPayload,
  LocalImportStatusResponse,
  LocalImportUploadResponse,
  VersionResponse,
  ConfigResponse,
  DuplicateGroupsResponse,
  LinkedGoogleAccount,
  GoogleOAuthStartResponse,
  PickerSessionCreateResponse,
  UserPreferencesResponse,
  UserPreferencesUpdateResponse,
} from '../types/api';
import { getApiErrorCode } from './apiErrors';

function extractApiErrorCode(error: any, fallback: string): string {
  return getApiErrorCode(error) || error.message || fallback;
}

class ApiClient {
  private client: AxiosInstance;

  constructor(baseURL: string = '/api') {
    this.client = axios.create({
      baseURL,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // リクエストインターセプター（認証トークン付与）
    this.client.interceptors.request.use(
      (config) => {
        const token = localStorage.getItem('access_token');
        if (token) {
          config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
      },
      (error) => Promise.reject(error)
    );

    // レスポンスインターセプター（エラーハンドリング）
    this.client.interceptors.response.use(
      (response) => response,
      async (error) => {
        // 認証エンドポイント自体の 401(資格情報不正・TOTP要求等)は
        // セッション失効とは異なるため、リフレッシュ/リダイレクトを行わない。
        const requestUrl: string = error.config?.url || '';
        const isAuthEndpoint =
          requestUrl.includes('/auth/login') ||
          requestUrl.includes('/auth/refresh');
        if (error.response?.status === 401 && !isAuthEndpoint) {
          // トークン期限切れの場合、リフレッシュトークンで再取得を試行
          const refreshToken = localStorage.getItem('refresh_token');
          if (refreshToken) {
            try {
              const refreshResponse = await this.refreshAccessToken(refreshToken);
              if (refreshResponse.success && refreshResponse.data) {
                localStorage.setItem('access_token', refreshResponse.data.access_token);
                // 元のリクエストを再実行
                return this.client.request(error.config);
              }
              // リフレッシュ失敗（refreshAccessToken は例外を投げず
              // success:false を返す。サーバー再起動でトークンが失効した
              // 場合など）。放置すると画面が止まったままになるため、
              // トークンを破棄してログイン画面へ遷移する。
              this.forceLogout();
            } catch (refreshError) {
              // リフレッシュ失敗時はログアウト
              this.forceLogout();
            }
          } else {
            // リフレッシュトークンがない場合はログアウト
            this.forceLogout();
          }
        }
        return Promise.reject(error);
      }
    );
  }

  // 認証情報を破棄してログイン画面へ遷移する（多重リダイレクト防止付き）
  private forceLogout(): void {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    if (window.location.pathname !== '/login') {
      window.location.href = '/login';
    }
  }

  // 基本的なHTTPメソッド
  private async get<T>(url: string, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
    const response: AxiosResponse<ApiResponse<T>> = await this.client.get(url, config);
    return response.data;
  }

  private async post<T>(url: string, data?: any, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
    const response: AxiosResponse<ApiResponse<T>> = await this.client.post(url, data, config);
    return response.data;
  }

  private async put<T>(url: string, data?: any, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
    const response: AxiosResponse<ApiResponse<T>> = await this.client.put(url, data, config);
    return response.data;
  }

  private async delete<T>(url: string, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
    const response: AxiosResponse<ApiResponse<T>> = await this.client.delete(url, config);
    return response.data;
  }

  // 認証API（Flask直接レスポンス用）
  async login(credentials: LoginRequest): Promise<ApiResponse<LoginResponse>> {
    try {
      // バックエンドは scope が空リクエストなら権限なしを発行する仕様のため、
      // ブラウザSPAは保有する全権限を要求する 'gui:view' を明示的に送る。
      const requestBody: LoginRequest = {
        ...credentials,
        scope: credentials.scope && credentials.scope.length > 0 ? credentials.scope : ['gui:view'],
      };
      const response = await this.client.post<LoginResponse>('/auth/login', requestBody);
      // Flask APIは直接データを返すので、ApiResponse形式に変換
      return {
        success: true,
        data: response.data
      };
    } catch (error: any) {
      return {
        success: false,
        message: extractApiErrorCode(error, 'ログインに失敗しました')
      };
    }
  }

  async register(userData: RegisterRequest): Promise<ApiResponse<User>> {
    return this.post<User>('/auth/register', userData);
  }

  async refreshAccessToken(refreshToken: string): Promise<ApiResponse<{ access_token: string }>> {
    try {
      const response = await this.client.post<{ access_token: string }>('/auth/refresh', { refresh_token: refreshToken });
      return {
        success: true,
        data: response.data
      };
    } catch (error: any) {
      return {
        success: false,
        message: extractApiErrorCode(error, 'トークン更新に失敗しました')
      };
    }
  }

  async logout(): Promise<ApiResponse<void>> {
    return this.post<void>('/auth/logout');
  }

  async getCurrentUser(): Promise<ApiResponse<User>> {
    try {
      const response = await this.client.get<User>('/auth/me');
      // Flask APIは直接データを返すので、ApiResponse形式に変換
      return {
        success: true,
        data: response.data
      };
    } catch (error: any) {
      return {
        success: false,
        message: extractApiErrorCode(error, 'ユーザー情報の取得に失敗しました')
      };
    }
  }

  async getUserRoles(): Promise<ApiResponse<any>> {
    try {
      const response = await this.client.get<any>('/auth/roles');
      return {
        success: true,
        data: response.data
      };
    } catch (error: any) {
      return {
        success: false,
        message: extractApiErrorCode(error, 'ロール情報の取得に失敗しました')
      };
    }
  }

  async selectRole(roleId: number): Promise<ApiResponse<any>> {
    try {
      const response = await this.client.post<any>('/auth/select-role', { role_id: roleId });
      return {
        success: true,
        data: response.data
      };
    } catch (error: any) {
      return {
        success: false,
        message: extractApiErrorCode(error, 'ロール選択に失敗しました')
      };
    }
  }

  async updateProfile(userData: Partial<User>): Promise<ApiResponse<User>> {
    return this.put<User>('/auth/profile', userData);
  }

  async updateUserProfile(data: ProfileUpdateRequest): Promise<ProfileUpdateResponse> {
    const response = await this.client.put<ProfileUpdateResponse>('/auth/profile', data);
    return response.data;
  }

  async getTOTPStatus(): Promise<TOTPStatusResponse> {
    const response = await this.client.get<TOTPStatusResponse>('/auth/2fa/status');
    return response.data;
  }

  async setupTOTP(): Promise<TOTPSetupResponse> {
    const response = await this.client.post<TOTPSetupResponse>('/auth/2fa/setup');
    return response.data;
  }

  async confirmTOTP(secret: string, code: string): Promise<{ enabled: boolean }> {
    const response = await this.client.post<{ enabled: boolean }>('/auth/2fa/confirm', { secret, code });
    return response.data;
  }

  async disableTOTP(): Promise<{ enabled: boolean }> {
    const response = await this.client.delete<{ enabled: boolean }>('/auth/2fa');
    return response.data;
  }

  async registerUser(data: RegisterUserRequest): Promise<RegisterUserResponse> {
    const response = await this.client.post<RegisterUserResponse>('/auth/register', data);
    return response.data;
  }

  // メディアAPI
  async getMediaList(params?: {
    page?: number;
    pageSize?: number;
    session_id?: string;
    media_type?: 'photo' | 'video';
    sort?: string;
  }): Promise<PaginatedResponse<Media>> {
    const response = await this.get<{ data: Media[]; pagination: any }>('/media', { params });
    return {
      ...response,
      data: response.data?.data || [],
      pagination: response.data?.pagination || {}
    } as PaginatedResponse<Media>;
  }

  async getMedia(id: string): Promise<ApiResponse<Media>> {
    return this.get<Media>(`/media/${id}`);
  }

  async getMediaThumbnailUrl(id: string, size: number): Promise<ApiResponse<{ url: string }>> {
    return this.post<{ url: string }>(`/media/${id}/thumb-url`, { size });
  }

  async getMediaPlaybackUrl(id: string): Promise<ApiResponse<{ url: string }>> {
    return this.post<{ url: string }>(`/media/${id}/playback-url`);
  }

  async deleteMedia(id: string): Promise<ApiResponse<void>> {
    return this.delete<void>(`/media/${id}`);
  }

  async getMediaDuplicates(limit?: number): Promise<DuplicateGroupsResponse> {
    const response = await this.client.get<DuplicateGroupsResponse>('/media/duplicates', {
      params: limit ? { limit } : undefined,
    });
    return response.data;
  }

  async bulkDeleteMedia(mediaIds: number[]): Promise<{ result?: string }> {
    const response = await this.client.post('/media/bulk-actions', {
      media_ids: mediaIds,
      action: 'delete',
    });
    return response.data;
  }

  // セッションAPI
  async getSessionList(params?: {
    page?: number;
    pageSize?: number;
    sort?: string;
  }): Promise<PaginatedResponse<MediaSession>> {
    const response = await this.get<{ data: MediaSession[]; pagination: any }>('/sessions', { params });
    return {
      ...response,
      data: response.data?.data || [],
      pagination: response.data?.pagination || {}
    } as PaginatedResponse<MediaSession>;
  }

  async getSession(id: string): Promise<ApiResponse<MediaSession>> {
    return this.get<MediaSession>(`/sessions/${id}`);
  }

  async createSession(sessionData: Omit<MediaSession, 'id' | 'created_at' | 'updated_at'>): Promise<ApiResponse<MediaSession>> {
    return this.post<MediaSession>('/sessions', sessionData);
  }

  async updateSession(id: string, sessionData: Partial<MediaSession>): Promise<ApiResponse<MediaSession>> {
    return this.put<MediaSession>(`/sessions/${id}`, sessionData);
  }

  async deleteSession(id: string): Promise<ApiResponse<void>> {
    return this.delete<void>(`/sessions/${id}`);
  }

  // アルバムAPI
  async getAlbumList(params?: {
    page?: number;
    pageSize?: number;
    sort?: string;
  }): Promise<PaginatedResponse<Album>> {
    const response = await this.get<{ data: Album[]; pagination: any }>('/albums', { params });
    return {
      ...response,
      data: response.data?.data || [],
      pagination: response.data?.pagination || {}
    } as PaginatedResponse<Album>;
  }

  async getAlbum(id: string): Promise<ApiResponse<Album>> {
    return this.get<Album>(`/albums/${id}`);
  }

  async createAlbum(albumData: Omit<Album, 'id' | 'created_at' | 'updated_at'>): Promise<ApiResponse<Album>> {
    return this.post<Album>('/albums', albumData);
  }

  async updateAlbum(id: string, albumData: Partial<Album>): Promise<ApiResponse<Album>> {
    return this.put<Album>(`/albums/${id}`, albumData);
  }

  async deleteAlbum(id: string): Promise<ApiResponse<void>> {
    return this.delete<void>(`/albums/${id}`);
  }

  // 管理機能API
  async getSystemSettings(): Promise<ApiResponse<SystemSettings>> {
    return this.get<SystemSettings>('/admin/system-settings');
  }

  async updateSystemSettings(settings: SystemSettings): Promise<ApiResponse<SystemSettings>> {
    return this.put<SystemSettings>('/admin/system-settings', settings);
  }

  async getGoogleAccounts(): Promise<ApiResponse<GoogleAccount[]>> {
    return this.get<GoogleAccount[]>('/admin/google-accounts');
  }

  async syncGooglePhotos(accountId: string): Promise<ApiResponse<TaskStatus>> {
    return this.post<TaskStatus>(`/admin/google-accounts/${accountId}/sync`);
  }

  // ===== Google アカウント連携（/api/google/*） =====

  async getLinkedGoogleAccounts(params?: { mine?: boolean }): Promise<CursorListResponse<LinkedGoogleAccount>> {
    const response = await this.client.get<CursorListResponse<LinkedGoogleAccount>>('/google/accounts', {
      params: params?.mine ? { mine: 1 } : undefined,
    });
    return response.data;
  }

  // Google アカウント登録: OAuth 認可 URL を取得する。呼び出し側で auth_url へ遷移する。
  async startGoogleAccountLink(redirect?: string): Promise<GoogleOAuthStartResponse> {
    const response = await this.client.post<GoogleOAuthStartResponse>('/google/oauth/start', {
      scope_profile: 'photo_picker',
      ...(redirect ? { redirect } : {}),
    });
    return response.data;
  }

  async updateGoogleAccountStatus(
    id: number,
    status: 'active' | 'disabled'
  ): Promise<{ result: string; status: string }> {
    const response = await this.client.patch<{ result: string; status: string }>(
      `/google/accounts/${id}`,
      { status }
    );
    return response.data;
  }

  async unlinkGoogleAccount(id: number): Promise<{ result: string }> {
    const response = await this.client.delete<{ result: string }>(`/google/accounts/${id}`);
    return response.data;
  }

  async testGoogleAccount(id: number): Promise<{ result: string }> {
    const response = await this.client.post<{ result: string }>(`/google/accounts/${id}/test`);
    return response.data;
  }

  // Google Photos Picker セッションを作成する（Photo インポートの入口）
  async createPickerSession(accountId?: number): Promise<PickerSessionCreateResponse> {
    const response = await this.client.post<PickerSessionCreateResponse>('/picker/session', {
      ...(accountId != null ? { account_id: accountId } : {}),
    });
    return response.data;
  }

  // タスク状況API
  async getTaskStatus(taskId: string): Promise<ApiResponse<TaskStatus>> {
    return this.get<TaskStatus>(`/tasks/${taskId}/status`);
  }

  // ===== 同期・変換ジョブ履歴 API =====
  // バックエンドは {jobs, pagination, ...} の生レスポンスを返すため、
  // ApiResponse ラップせず素の型で受ける。
  async getSyncJobs(params?: SyncJobsQuery): Promise<SyncJobListResponse> {
    const response = await this.client.get<SyncJobListResponse>('/sync/jobs', { params });
    return response.data;
  }

  async getSyncJob(id: number): Promise<SyncJobDetailResponse> {
    const response = await this.client.get<SyncJobDetailResponse>(`/sync/jobs/${id}`);
    return response.data;
  }

  async retrySyncJob(id: number): Promise<{
    success: boolean;
    retriedFrom: number;
    newJobId: number;
    taskId: string | null;
  }> {
    const response = await this.client.post(`/sync/jobs/${id}/retry`);
    return response.data;
  }

  // ===== Picker セッション一覧 API（実エンドポイント /picker/sessions） =====
  async getPickerSessions(params?: {
    page?: number;
    pageSize?: number;
  }): Promise<PickerSessionListResponse> {
    const response = await this.client.get<PickerSessionListResponse>('/picker/sessions', { params });
    return response.data;
  }

  async getPickerSessionStatus(sessionId: string): Promise<PickerSessionStatus> {
    const response = await this.client.get<PickerSessionStatus>(`/picker/session/${encodeURIComponent(sessionId)}`);
    return response.data;
  }

  // Google フォト側で選択が確定したセッションの取り込みを開始する
  // （選択されたメディア一覧を取得して取り込みキューへ投入）
  async startPickerSessionImport(sessionId: string): Promise<{ saved?: number; duplicates?: number }> {
    const response = await this.client.post<{ saved?: number; duplicates?: number }>(
      '/picker/session/mediaItems',
      { sessionId }
    );
    return response.data;
  }

  async getPickerSessionSelections(sessionId: string, params?: {
    page?: number;
    pageSize?: number;
    status?: string[];
    search?: string;
  }): Promise<PickerSessionSelectionsResponse> {
    const response = await this.client.get<PickerSessionSelectionsResponse>(
      `/picker/session/${encodeURIComponent(sessionId)}/selections`,
      { params }
    );
    return response.data;
  }

  async getPickerSessionLogs(sessionId: string, params?: {
    limit?: number;
    cursor?: number;
    after?: number;
  }): Promise<PickerSessionLogsResponse> {
    const response = await this.client.get<PickerSessionLogsResponse>(
      `/picker/session/${encodeURIComponent(sessionId)}/logs`,
      { params }
    );
    return response.data;
  }

  async getPickerSelectionError(sessionId: string, selectionId: number): Promise<SelectionErrorPayload> {
    const response = await this.client.get<SelectionErrorPayload>(
      `/picker/session/${encodeURIComponent(sessionId)}/selections/${selectionId}/error`
    );
    return response.data;
  }

  async getLocalImportStatus(): Promise<LocalImportStatusResponse> {
    const response = await this.client.get<LocalImportStatusResponse>('/sync/local-import/status');
    return response.data;
  }

  async triggerLocalImport(opts?: { duplicateRegeneration?: string }): Promise<{ success: boolean; session_id?: string }> {
    const response = await this.client.post<{ success: boolean; session_id?: string }>('/sync/local-import', opts ?? {});
    return response.data;
  }

  async uploadLocalImportFiles(files: File[]): Promise<LocalImportUploadResponse> {
    const formData = new FormData();
    files.forEach((file) => formData.append('files', file));
    const response = await this.client.post<LocalImportUploadResponse>(
      '/sync/local-import/upload',
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    );
    return response.data;
  }

  // ===== バージョン情報 =====

  async getVersion(): Promise<VersionResponse> {
    const response = await this.client.get<VersionResponse>('/version');
    return response.data;
  }

  // ===== アプリケーション設定 (/admin/config) =====
  async getConfig(): Promise<ConfigResponse> {
    const response = await this.client.get<ConfigResponse>('/admin/config');
    return response.data;
  }

  async updateConfig(payload: { updates?: Record<string, any>; resetKeys?: string[] }): Promise<ConfigResponse> {
    const response = await this.client.put<ConfigResponse>('/admin/config', payload);
    return response.data;
  }

  async updateConfigCors(payload: { allowedOrigins?: string[]; reset?: boolean }): Promise<ConfigResponse> {
    const response = await this.client.put<ConfigResponse>('/admin/config/cors', payload);
    return response.data;
  }

  async updateConfigSigning(payload: { mode: string; secret?: string; groupCode?: string }): Promise<ConfigResponse> {
    const response = await this.client.put<ConfigResponse>('/admin/config/signing', payload);
    return response.data;
  }

  // ===== 写真管理 API（実エンドポイントの生レスポンスで受ける） =====
  async getPhotos(params?: {
    pageSize?: number;
    cursor?: string;
    // メディア種別フィルタ（バックエンドの ?type= パラメータ）
    type?: 'photo' | 'video';
    // タグ ID のカンマ区切り（すべて含むメディアのみ）
    tags?: string;
    // 撮影日時の範囲（ISO 8601）
    after?: string;
    before?: string;
    order?: 'asc' | 'desc';
  }): Promise<CursorListResponse<PhotoItem>> {
    const response = await this.client.get<CursorListResponse<PhotoItem>>('/media', { params });
    return response.data;
  }

  async getPhoto(id: number): Promise<PhotoItem> {
    const response = await this.client.get<PhotoItem>(`/media/${id}`);
    return response.data;
  }

  async getPhotoThumbUrl(id: number, size: number): Promise<string | null> {
    const response = await this.client.post<{ url?: string }>(`/media/${id}/thumb-url`, { size });
    return response.data?.url ?? null;
  }

  async getPhotoPlaybackUrl(id: number): Promise<string | null> {
    const response = await this.client.post<{ url?: string }>(`/media/${id}/playback-url`);
    return response.data?.url ?? null;
  }

  async getAlbums(params?: {
    pageSize?: number;
    cursor?: string;
    q?: string;
  }): Promise<CursorListResponse<AlbumSummary>> {
    const response = await this.client.get<CursorListResponse<AlbumSummary>>('/albums', { params });
    return response.data;
  }

  async getTags(params?: { q?: string; limit?: number }): Promise<{ items: MediaTag[] }> {
    const response = await this.client.get<{ items: MediaTag[] }>('/tags', { params });
    return response.data;
  }

  // ===== アルバム CRUD / 並び替え =====

  async getAlbumDetail(id: number): Promise<{ album: AlbumDetail }> {
    const response = await this.client.get<{ album: AlbumDetail }>(`/albums/${id}`);
    return response.data;
  }

  async createAlbumItem(data: {
    name: string;
    description?: string;
    visibility?: string;
    mediaIds?: number[];
    coverMediaId?: number;
  }): Promise<{ album: AlbumDetail; created: boolean }> {
    const response = await this.client.post<{ album: AlbumDetail; created: boolean }>('/albums', data);
    return response.data;
  }

  async updateAlbumItem(
    id: number,
    data: {
      name?: string;
      description?: string;
      visibility?: string;
      mediaIds?: number[];
      coverMediaId?: number;
    }
  ): Promise<{ album: AlbumDetail; updated: boolean }> {
    const response = await this.client.put<{ album: AlbumDetail; updated: boolean }>(`/albums/${id}`, data);
    return response.data;
  }

  async deleteAlbumItem(id: number): Promise<{ result: string }> {
    const response = await this.client.delete<{ result: string }>(`/albums/${id}`);
    return response.data;
  }

  async reorderAlbumMedia(albumId: number, mediaIds: number[]): Promise<{ updated: boolean; album: AlbumDetail }> {
    const response = await this.client.put<{ updated: boolean; album: AlbumDetail }>(
      `/albums/${albumId}/media/order`,
      { mediaIds }
    );
    return response.data;
  }

  // ===== タグ作成 =====

  async createTag(name: string, attr: string): Promise<{ tag: MediaTag; created: boolean }> {
    const response = await this.client.post<{ tag: MediaTag; created: boolean }>('/tags', { name, attr });
    return response.data;
  }

  // ===== メディアタグ付与 =====

  async updateMediaTags(mediaId: number, tagIds: number[]): Promise<{ tags: MediaTag[] }> {
    const response = await this.client.put<{ tags: MediaTag[] }>(`/media/${mediaId}/tags`, { tag_ids: tagIds });
    return response.data;
  }

  // ===== 管理 API — ユーザー管理 =====

  async getAdminUsers(params?: { q?: string }): Promise<{ users: AdminUser[] }> {
    const response = await this.client.get<{ users: AdminUser[] }>('/admin/users', { params });
    return response.data;
  }

  async getAdminUser(id: number): Promise<{ user: AdminUser }> {
    const response = await this.client.get<{ user: AdminUser }>(`/admin/users/${id}`);
    return response.data;
  }

  async createAdminUser(data: {
    email: string;
    username?: string;
    password: string;
    roleIds?: number[];
  }): Promise<{ user: AdminUser; created: boolean }> {
    const response = await this.client.post<{ user: AdminUser; created: boolean }>('/admin/users', data);
    return response.data;
  }

  async updateAdminUser(
    id: number,
    data: { email?: string; username?: string | null; isActive?: boolean }
  ): Promise<{ user: AdminUser; updated: boolean }> {
    const response = await this.client.put<{ user: AdminUser; updated: boolean }>(`/admin/users/${id}`, data);
    return response.data;
  }

  async updateAdminUserRoles(id: number, roleIds: number[]): Promise<{ user: AdminUser; updated: boolean }> {
    const response = await this.client.put<{ user: AdminUser; updated: boolean }>(
      `/admin/users/${id}/roles`,
      { roleIds }
    );
    return response.data;
  }

  async resetAdminUserTOTP(id: number): Promise<{ result: string; userId: number }> {
    const response = await this.client.post<{ result: string; userId: number }>(
      `/admin/users/${id}/reset-totp`
    );
    return response.data;
  }

  async deleteAdminUser(id: number): Promise<{ result: string; userId: number }> {
    const response = await this.client.delete<{ result: string; userId: number }>(`/admin/users/${id}`);
    return response.data;
  }

  async getAdminRoles(): Promise<{ roles: AdminRole[] }> {
    const response = await this.client.get<{ roles: AdminRole[] }>('/admin/roles');
    return response.data;
  }

  // ===== 管理 API — ロール CRUD =====

  async createAdminRole(data: { name: string; permissionIds?: number[] }): Promise<{ role: AdminRoleDetail; created: boolean }> {
    const response = await this.client.post<{ role: AdminRoleDetail; created: boolean }>('/admin/roles', data);
    return response.data;
  }

  async getAdminRoleDetail(id: number): Promise<{ role: AdminRoleDetail }> {
    const response = await this.client.get<{ role: AdminRoleDetail }>(`/admin/roles/${id}`);
    return response.data;
  }

  async updateAdminRole(id: number, data: { name?: string; permissionIds?: number[] }): Promise<{ role: AdminRoleDetail; updated: boolean }> {
    const response = await this.client.put<{ role: AdminRoleDetail; updated: boolean }>(`/admin/roles/${id}`, data);
    return response.data;
  }

  async deleteAdminRole(id: number): Promise<{ result: string }> {
    const response = await this.client.delete<{ result: string }>(`/admin/roles/${id}`);
    return response.data;
  }

  // ===== 管理 API — グループ CRUD =====

  async getAdminGroups(): Promise<{ groups: AdminGroup[] }> {
    const response = await this.client.get<{ groups: AdminGroup[] }>('/admin/groups');
    return response.data;
  }

  async createAdminGroup(data: { name: string; description?: string; parentId?: number | null }): Promise<{ group: AdminGroup; created: boolean }> {
    const response = await this.client.post<{ group: AdminGroup; created: boolean }>('/admin/groups', data);
    return response.data;
  }

  async getAdminGroupDetail(id: number): Promise<{ group: AdminGroupDetail }> {
    const response = await this.client.get<{ group: AdminGroupDetail }>(`/admin/groups/${id}`);
    return response.data;
  }

  async updateAdminGroup(id: number, data: { name?: string; description?: string; parentId?: number | null; memberIds?: number[] }): Promise<{ group: AdminGroup; updated: boolean }> {
    const response = await this.client.put<{ group: AdminGroup; updated: boolean }>(`/admin/groups/${id}`, data);
    return response.data;
  }

  async deleteAdminGroup(id: number): Promise<{ result: string }> {
    const response = await this.client.delete<{ result: string }>(`/admin/groups/${id}`);
    return response.data;
  }

  // ===== 管理 API — 権限 CRUD =====

  async getAdminPermissions(params?: { q?: string }): Promise<{ permissions: AdminPermission[] }> {
    const response = await this.client.get<{ permissions: AdminPermission[] }>('/admin/permissions', { params });
    return response.data;
  }

  async createAdminPermission(data: { code: string; detail?: string }): Promise<{ permission: AdminPermission; created: boolean }> {
    const response = await this.client.post<{ permission: AdminPermission; created: boolean }>('/admin/permissions', data);
    return response.data;
  }

  async updateAdminPermission(id: number, data: { code?: string; detail?: string }): Promise<{ permission: AdminPermission; updated: boolean }> {
    const response = await this.client.put<{ permission: AdminPermission; updated: boolean }>(`/admin/permissions/${id}`, data);
    return response.data;
  }

  async deleteAdminPermission(id: number): Promise<{ result: string }> {
    const response = await this.client.delete<{ result: string }>(`/admin/permissions/${id}`);
    return response.data;
  }

  // ===== 管理 API — サービスアカウント CRUD =====

  async getAdminServiceAccounts(params?: { q?: string }): Promise<{ serviceAccounts: AdminServiceAccount[] }> {
    const response = await this.client.get<{ serviceAccounts: AdminServiceAccount[] }>('/admin/service-accounts', { params });
    return response.data;
  }

  async createAdminServiceAccount(data: { name: string; description?: string; scopes?: string[]; isActive?: boolean }): Promise<{ serviceAccount: AdminServiceAccount; created: boolean }> {
    const response = await this.client.post<{ serviceAccount: AdminServiceAccount; created: boolean }>('/admin/service-accounts', data);
    return response.data;
  }

  async updateAdminServiceAccount(id: number, data: { name?: string; description?: string; scopes?: string[]; isActive?: boolean }): Promise<{ serviceAccount: AdminServiceAccount; updated: boolean }> {
    const response = await this.client.put<{ serviceAccount: AdminServiceAccount; updated: boolean }>(`/admin/service-accounts/${id}`, data);
    return response.data;
  }

  async deleteAdminServiceAccount(id: number): Promise<{ result: string }> {
    const response = await this.client.delete<{ result: string }>(`/admin/service-accounts/${id}`);
    return response.data;
  }

  // ===== 管理 API — ダッシュボード =====

  async getAdminDashboard(): Promise<{ stats: DashboardStats }> {
    const response = await this.client.get<{ stats: DashboardStats }>('/admin/dashboard');
    return response.data;
  }

  // ===== パスキー管理 =====

  async getPasskeys(): Promise<{ passkeys: PasskeyItem[] }> {
    const response = await this.client.get<{ passkeys: PasskeyItem[] }>('/auth/passkeys');
    return response.data;
  }

  async deletePasskey(id: number): Promise<{ result: string }> {
    const response = await this.client.delete<{ result: string }>(`/auth/passkeys/${id}`);
    return response.data;
  }

  async getPasskeyRegisterOptions(): Promise<Record<string, unknown>> {
    const response = await this.client.get<Record<string, unknown>>('/auth/passkey/options/register');
    return response.data;
  }

  async verifyPasskeyRegister(credential: Record<string, unknown>): Promise<{ result: string }> {
    const response = await this.client.post<{ result: string }>('/auth/passkey/verify/register', credential);
    return response.data;
  }

  // ===== パスワードリセット =====

  async forgotPassword(email: string): Promise<{ sent: boolean }> {
    const response = await this.client.post<{ sent: boolean }>('/auth/password/forgot', { email });
    return response.data;
  }

  async resetPassword(token: string, password: string): Promise<{ reset: boolean }> {
    const response = await this.client.post<{ reset: boolean }>('/auth/password/reset', { token, password });
    return response.data;
  }

  async forceChangePassword(password: string, currentPassword?: string): Promise<{ changed: boolean }> {
    const body: Record<string, string> = { password };
    if (currentPassword) body.current_password = currentPassword;
    const response = await this.client.post<{ changed: boolean }>('/auth/password/force-change', body);
    return response.data;
  }

  // ===== Photo Exports =====

  async previewPhotoExports(params: { dateFrom?: string; dateTo?: string; limit?: number }): Promise<{
    matchedCount: number;
    exportCount: number;
    totalBytes: number;
    limit: number;
  }> {
    const query = new URLSearchParams();
    if (params.dateFrom) query.set('dateFrom', params.dateFrom);
    if (params.dateTo) query.set('dateTo', params.dateTo);
    if (params.limit !== undefined) query.set('limit', String(params.limit));
    const response = await this.client.get<{
      matchedCount: number;
      exportCount: number;
      totalBytes: number;
      limit: number;
    }>(`/admin/photo-exports/preview?${query.toString()}`);
    return response.data;
  }

  async downloadPhotoExports(
    params: { dateFrom?: string; dateTo?: string; limit?: number },
  ): Promise<void> {
    const query = new URLSearchParams();
    if (params.dateFrom) query.set('dateFrom', params.dateFrom);
    if (params.dateTo) query.set('dateTo', params.dateTo);
    if (params.limit !== undefined) query.set('limit', String(params.limit));

    const token = localStorage.getItem('access_token');
    const headers: Record<string, string> = {};
    if (token) headers['Authorization'] = 'Bearer ' + token;

    const response = await fetch(`/api/admin/photo-exports/download?${query.toString()}`, { headers });
    if (!response.ok) {
      throw new Error(`Export failed: ${response.status}`);
    }

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const disposition = response.headers.get('Content-Disposition') || '';
    const match = disposition.match(/filename="([^"]+)"/);
    a.download = match ? match[1] : 'photo_exports.zip';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }
  // ===== ユーザー設定 =====

  async getUserPreferences(): Promise<UserPreferencesResponse> {
    const response = await this.client.get<UserPreferencesResponse>('/user/preferences');
    return response.data;
  }

  async updateUserPreferences(prefs: Partial<{ slideshow_interval: number }>): Promise<UserPreferencesUpdateResponse> {
    const response = await this.client.put<UserPreferencesUpdateResponse>('/user/preferences', prefs);
    return response.data;
  }
}

export const apiClient = new ApiClient();
export default apiClient;
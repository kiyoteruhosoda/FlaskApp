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
} from '../types/api';

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
            } catch (refreshError) {
              // リフレッシュ失敗時はログアウト
              localStorage.removeItem('access_token');
              localStorage.removeItem('refresh_token');
              window.location.href = '/login';
            }
          } else {
            // リフレッシュトークンがない場合はログアウト
            localStorage.removeItem('access_token');
            localStorage.removeItem('refresh_token');
            window.location.href = '/login';
          }
        }
        return Promise.reject(error);
      }
    );
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
      const response = await this.client.post<LoginResponse>('/auth/login', credentials);
      // Flask APIは直接データを返すので、ApiResponse形式に変換
      return {
        success: true,
        data: response.data
      };
    } catch (error: any) {
      return {
        success: false,
        message: error.response?.data?.error || error.message || 'ログインに失敗しました'
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
        message: error.response?.data?.error || 'トークン更新に失敗しました'
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
        message: error.response?.data?.error || 'ユーザー情報の取得に失敗しました'
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
        message: error.response?.data?.error || 'ロール情報の取得に失敗しました'
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
        message: error.response?.data?.error || 'ロール選択に失敗しました'
      };
    }
  }

  async updateProfile(userData: Partial<User>): Promise<ApiResponse<User>> {
    return this.put<User>('/auth/profile', userData);
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

  // ===== 写真管理 API（実エンドポイントの生レスポンスで受ける） =====
  async getPhotos(params?: {
    pageSize?: number;
    cursor?: string;
    is_video?: 0 | 1;
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
}

export const apiClient = new ApiClient();
export default apiClient;
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
  TaskStatus
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
        if (error.response?.status === 401) {
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
}

export const apiClient = new ApiClient();
export default apiClient;
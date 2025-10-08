/**
 * APIクライアント - セッション切れ時の自動リフレッシュ機能付き
 */

class APIClient {
  constructor() {
    this.isRefreshing = false;
    this.failedQueue = [];
    this.maxRetries = 1;
  }

  /**
   * トークンリフレッシュを実行
   */
  async refreshToken() {
    const refreshToken = localStorage.getItem('refresh_token');
    if (!refreshToken) {
      console.error('APIClient: No refresh token available');
      throw new Error('No refresh token available');
    }

    console.log('APIClient: Attempting to refresh token...');
    const response = await fetch('/api/refresh', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        refresh_token: refreshToken
      })
    });

    if (!response.ok) {
      console.error(`APIClient: Token refresh failed with status ${response.status}`);
      localStorage.removeItem('refresh_token');
      throw new Error(`Token refresh failed: ${response.status}`);
    }

    const data = await response.json();
    console.log('APIClient: Token refresh successful');
    
    if (data.refresh_token) {
      localStorage.setItem('refresh_token', data.refresh_token);
    }
    
    // アクセストークンがCookieに自動設定されるので、追加の処理は不要
    return data;
  }

  /**
   * 失敗したリクエストをキューに追加
   */
  addToFailedQueue(resolve, reject, config) {
    this.failedQueue.push({ resolve, reject, config });
  }

  /**
   * 失敗したリクエストキューを処理
   */
  processQueue(error = null) {
    this.failedQueue.forEach(({ resolve, reject, config }) => {
      if (error) {
        reject(error);
      } else {
        resolve(this.request(config));
      }
    });
    this.failedQueue = [];
  }

  /**
   * APIリクエストを実行（リトライ機能付き）
   */
  async request(config, retryCount = 0) {
    const { url, method = 'GET', headers = {}, body, ...options } = config;

    // CSRFトークンを自動で追加
    const csrfToken = this.getCsrfTokenFromCookie();
    if (csrfToken && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method.toUpperCase())) {
      headers['X-CSRFToken'] = csrfToken;
    }

    const isFormData = typeof FormData !== 'undefined' && body instanceof FormData;
    const isURLSearchParams = typeof URLSearchParams !== 'undefined' && body instanceof URLSearchParams;
    const isBlob = typeof Blob !== 'undefined' && body instanceof Blob;
    const isArrayBuffer = typeof ArrayBuffer !== 'undefined' && body instanceof ArrayBuffer;
    const isDataView = typeof DataView !== 'undefined' && body instanceof DataView;
    const shouldSerializeJson = (
      body &&
      typeof body === 'object' &&
      !isFormData &&
      !isURLSearchParams &&
      !isBlob &&
      !isArrayBuffer &&
      !isDataView
    );

    if (shouldSerializeJson && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }

    const requestConfig = {
      method,
      headers,
      body: shouldSerializeJson ? JSON.stringify(body) : body,
      ...options
    };

    try {
      const response = await fetch(url, requestConfig);

      // 401エラーでリフレッシュトークンが利用可能な場合
      if (response.status === 401 && retryCount < this.maxRetries) {
        console.log('APIClient: Received 401, attempting token refresh...');
        
        if (this.isRefreshing) {
          // 既にリフレッシュ中の場合はキューに追加
          console.log('APIClient: Already refreshing, adding to queue...');
          return new Promise((resolve, reject) => {
            this.addToFailedQueue(resolve, reject, config);
          });
        }

        this.isRefreshing = true;

        try {
          await this.refreshToken();
          this.isRefreshing = false;
          this.processQueue();
          
          console.log('APIClient: Token refresh successful, retrying original request...');
          // リフレッシュ成功後にリクエストを再実行
          return this.request(config, retryCount + 1);
        } catch (refreshError) {
          console.error('APIClient: Token refresh failed:', refreshError);
          this.isRefreshing = false;
          this.processQueue(refreshError);
          
          // リフレッシュに失敗した場合はログインページにリダイレクト
          this.redirectToLogin();
          throw refreshError;
        }
      }

      return response;
    } catch (error) {
      if (retryCount < this.maxRetries && !error.name?.includes('TypeError')) {
        return this.request(config, retryCount + 1);
      }
      throw error;
    }
  }

  /**
   * CSRFトークンをCookieから取得
   */
  getCsrfTokenFromCookie() {
    const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : null;
  }

  /**
   * ログインページにリダイレクト
   */
  redirectToLogin() {
    // 現在のページをリダイレクト先として保存
    const currentPath = window.location.pathname + window.location.search;
    if (currentPath !== '/auth/login') {
      localStorage.setItem('redirect_after_login', currentPath);
    }
    
    // トーストメッセージを表示
    if (typeof showErrorToast === 'function') {
      showErrorToast('セッションが期限切れです。再度ログインしてください。');
    }
    
    // 少し遅延を入れてリダイレクト
    setTimeout(() => {
      window.location.href = '/auth/login';
    }, 1000);
  }

  /**
   * GET リクエスト
   */
  async get(url, config = {}) {
    return this.request({ url, method: 'GET', ...config });
  }

  /**
   * POST リクエスト
   */
  async post(url, body, config = {}) {
    return this.request({ url, method: 'POST', body, ...config });
  }

  /**
   * PUT リクエスト
   */
  async put(url, body, config = {}) {
    return this.request({ url, method: 'PUT', body, ...config });
  }

  /**
   * PATCH リクエスト
   */
  async patch(url, body, config = {}) {
    return this.request({ url, method: 'PATCH', body, ...config });
  }

  /**
   * DELETE リクエスト
   */
  async delete(url, config = {}) {
    return this.request({ url, method: 'DELETE', ...config });
  }

  /**
   * JSONレスポンスを取得するヘルパー
   */
  async getJSON(url, config = {}) {
    const response = await this.get(url, config);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    return response.json();
  }

  /**
   * POST JSONレスポンスを取得するヘルパー
   */
  async postJSON(url, body, config = {}) {
    const response = await this.post(url, body, config);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    return response.json();
  }
}

// グローバルインスタンスを作成
window.apiClient = new APIClient();

/**
 * ログイン後のリダイレクト処理
 */
function handleLoginRedirect() {
  const redirectPath = localStorage.getItem('redirect_after_login');
  if (redirectPath) {
    localStorage.removeItem('redirect_after_login');
    window.location.href = redirectPath;
  }
}

// ログインページでリダイレクト処理を実行
if (window.location.pathname === '/auth/login') {
  document.addEventListener('DOMContentLoaded', () => {
    // ログイン成功後のフォーム送信を検知
    const loginForm = document.querySelector('form[action*="login"]');
    if (loginForm) {
      loginForm.addEventListener('submit', () => {
        // ログイン成功後にリダイレクト処理を実行するためのフラグを設定
        setTimeout(handleLoginRedirect, 1000);
      });
    }
  });
}

/**
 * API client with automatic token refresh when the session expires
 */

class APIClient {
  constructor() {
    this.isRefreshing = false;
    this.failedQueue = [];
    this.maxRetries = 1;
  }

  /**
   * Perform a token refresh
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
    
    // Access tokens are automatically managed via cookies, so no extra handling is required
    return data;
  }

  /**
   * Queue failed requests
   */
  addToFailedQueue(resolve, reject, config) {
    this.failedQueue.push({ resolve, reject, config });
  }

  /**
   * Process queued failed requests
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
   * Perform an API request with retry support
   */
  async request(config, retryCount = 0) {
    const { url, method = 'GET', headers = {}, body, ...options } = config;

    // Automatically attach the CSRF token
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

      // Handle 401 responses when a refresh token is available
      if (response.status === 401 && retryCount < this.maxRetries) {
        console.log('APIClient: Received 401, attempting token refresh...');
        
        if (this.isRefreshing) {
          // Queue the request if a refresh is already in progress
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
          // Retry the original request after a successful refresh
          return this.request(config, retryCount + 1);
        } catch (refreshError) {
          console.error('APIClient: Token refresh failed:', refreshError);
          this.isRefreshing = false;
          this.processQueue(refreshError);
          
          // Redirect to the login page if refreshing fails
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
   * Retrieve the CSRF token from cookies
   */
  getCsrfTokenFromCookie() {
    const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : null;
  }

  /**
   * Redirect to the login page
   */
  redirectToLogin() {
    // Remember the current page for redirect after login
    const currentPath = window.location.pathname + window.location.search;
    if (currentPath !== '/auth/login') {
      localStorage.setItem('redirect_after_login', currentPath);
    }
    
    // Show toast message when the session expires
    if (typeof showErrorToast === 'function') {
      showErrorToast(_('app.sessionExpired', 'Session expired. Please log in again.'));
    }
    
    // Redirect after a short delay
    setTimeout(() => {
      window.location.href = '/auth/login';
    }, 1000);
  }

  /**
   * Perform a GET request
   */
  async get(url, config = {}) {
    return this.request({ url, method: 'GET', ...config });
  }

  /**
   * Perform a POST request
   */
  async post(url, body, config = {}) {
    return this.request({ url, method: 'POST', body, ...config });
  }

  /**
   * Perform a PUT request
   */
  async put(url, body, config = {}) {
    return this.request({ url, method: 'PUT', body, ...config });
  }

  /**
   * Perform a PATCH request
   */
  async patch(url, body, config = {}) {
    return this.request({ url, method: 'PATCH', body, ...config });
  }

  /**
   * Perform a DELETE request
   */
  async delete(url, config = {}) {
    return this.request({ url, method: 'DELETE', ...config });
  }

  /**
   * Helper to retrieve a JSON response
   */
  async getJSON(url, config = {}) {
    const response = await this.get(url, config);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    return response.json();
  }

  /**
   * Helper to perform a POST request and parse JSON
   */
  async postJSON(url, body, config = {}) {
    const response = await this.post(url, body, config);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    return response.json();
  }
}

// Create a global instance
window.apiClient = new APIClient();

/**
 * Handle redirect logic after login
 */
function handleLoginRedirect() {
  const redirectPath = localStorage.getItem('redirect_after_login');
  if (redirectPath) {
    localStorage.removeItem('redirect_after_login');
    window.location.href = redirectPath;
  }
}

// Run redirect handling on the login page
if (window.location.pathname === '/auth/login') {
  document.addEventListener('DOMContentLoaded', () => {
    // Detect form submission after a successful login
    const loginForm = document.querySelector('form[action*="login"]');
    if (loginForm) {
      loginForm.addEventListener('submit', () => {
        // Set a flag so redirect handling runs after login
        setTimeout(handleLoginRedirect, 1000);
      });
    }
  });
}

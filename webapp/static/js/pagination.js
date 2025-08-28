/**
 * 共通ページング機能 - 無限スクロール対応
 * 
 * PhotoNestアプリケーション用の統一されたページング処理クライアント
 */

class PaginationClient {
    constructor(options = {}) {
        this.baseUrl = options.baseUrl || '';
        this.pageSize = options.pageSize || 200;
        this.autoLoad = options.autoLoad !== false;
        this.loadThreshold = options.loadThreshold || 0.8;
        
        // コールバック関数
        this.onItemsLoaded = options.onItemsLoaded || (() => {});
        this.onError = options.onError || ((error) => console.error('Pagination error:', error));
        this.onLoadingStateChange = options.onLoadingStateChange || (() => {});
        
        // 状態管理
        this.isLoading = false;
        this.hasNext = true;
        this.currentCursor = null;
        this.currentPage = 1;
        this.items = [];
        
        // スクロール監視
        this.scrollContainer = options.scrollContainer || window;
        this.scrollListener = null;
        
        if (this.autoLoad) {
            this.setupScrollListener();
        }
    }
    
    /**
     * スクロール監視の設定
     */
    setupScrollListener() {
        this.scrollListener = this.throttle(() => {
            if (this.shouldLoadMore()) {
                this.loadNext();
            }
        }, 200);
        
        this.scrollContainer.addEventListener('scroll', this.scrollListener);
    }
    
    /**
     * スクロール監視の停止
     */
    destroyScrollListener() {
        if (this.scrollListener) {
            this.scrollContainer.removeEventListener('scroll', this.scrollListener);
            this.scrollListener = null;
        }
    }
    
    /**
     * 追加読み込みが必要かチェック
     */
    shouldLoadMore() {
        if (this.isLoading || !this.hasNext) {
            return false;
        }
        
        const container = this.scrollContainer === window ? document.documentElement : this.scrollContainer;
        const scrollTop = this.scrollContainer === window ? window.pageYOffset : container.scrollTop;
        const scrollHeight = container.scrollHeight;
        const clientHeight = this.scrollContainer === window ? window.innerHeight : container.clientHeight;
        
        const scrollRatio = (scrollTop + clientHeight) / scrollHeight;
        return scrollRatio >= this.loadThreshold;
    }
    
    /**
     * 最初のページを読み込み
     */
    async loadFirst(params = {}) {
        this.reset();
        return this.loadNext(params);
    }
    
    /**
     * 次のページを読み込み
     */
    async loadNext(params = {}) {
        if (this.isLoading || !this.hasNext) {
            return;
        }
        
        this.setLoading(true);
        
        try {
            const queryParams = {
                pageSize: this.pageSize,
                ...params
            };
            
            // カーソーベースページング
            if (this.currentCursor) {
                queryParams.cursor = this.currentCursor;
            } else if (!this.currentCursor && this.currentPage > 1) {
                // オフセットベースページング
                queryParams.page = this.currentPage;
            }
            
            const url = this.buildUrl(queryParams);
            const response = await fetch(url, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    ...this.getAuthHeaders()
                }
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            // レスポンス形式の正規化
            const normalizedData = this.normalizeResponse(data);
            
            // 状態更新
            this.items.push(...normalizedData.items);
            this.hasNext = normalizedData.hasNext;
            this.currentCursor = normalizedData.nextCursor;
            this.currentPage++;
            
            // コールバック実行
            this.onItemsLoaded(normalizedData.items, {
                hasNext: this.hasNext,
                total: normalizedData.totalCount,
                currentPage: this.currentPage - 1
            });
            
        } catch (error) {
            this.onError(error);
        } finally {
            this.setLoading(false);
        }
    }
    
    /**
     * 状態をリセット
     */
    reset() {
        this.items = [];
        this.currentCursor = null;
        this.currentPage = 1;
        this.hasNext = true;
        this.isLoading = false;
    }
    
    /**
     * URLを構築
     */
    buildUrl(params) {
        const url = new URL(this.baseUrl, window.location.origin);
        Object.entries(params).forEach(([key, value]) => {
            if (value !== null && value !== undefined) {
                url.searchParams.append(key, value);
            }
        });
        return url.toString();
    }
    
    /**
     * 認証ヘッダーを取得
     */
    getAuthHeaders() {
        const headers = {};
        
        // CSRF トークン
        const csrfToken = this.getCsrfToken();
        if (csrfToken) {
            headers['X-CSRFToken'] = csrfToken;
        }
        
        return headers;
    }
    
    /**
     * CSRFトークンを取得
     */
    getCsrfToken() {
        const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : null;
    }
    
    /**
     * レスポンス形式を正規化
     */
    normalizeResponse(data) {
        // 直接アイテムが返される場合
        if (data.items) {
            return {
                items: data.items,
                hasNext: data.hasNext || false,
                nextCursor: data.nextCursor,
                totalCount: data.totalCount
            };
        }
        
        // sessionsList形式の場合
        if (data.sessions) {
            return {
                items: data.sessions,
                hasNext: data.pagination?.hasNext || false,
                nextCursor: data.pagination?.nextCursor,
                totalCount: data.pagination?.totalCount
            };
        }
        
        // selections形式の場合
        if (data.selections) {
            return {
                items: data.selections,
                hasNext: data.pagination?.hasNext || false,
                nextCursor: data.pagination?.nextCursor,
                totalCount: data.pagination?.totalCount
            };
        }
        
        // フォールバック
        return {
            items: [],
            hasNext: false,
            nextCursor: null,
            totalCount: 0
        };
    }
    
    /**
     * ローディング状態を設定
     */
    setLoading(loading) {
        this.isLoading = loading;
        this.onLoadingStateChange(loading);
    }
    
    /**
     * スロットル関数
     */
    throttle(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }
    
    /**
     * 破棄処理
     */
    destroy() {
        this.destroyScrollListener();
        this.reset();
    }
}

/**
 * 無限スクロール用のヘルパー関数
 */
class InfiniteScrollHelper {
    constructor(containerSelector, itemRenderer, options = {}) {
        this.container = document.querySelector(containerSelector);
        if (!this.container) {
            throw new Error(`Container not found: ${containerSelector}`);
        }
        
        this.itemRenderer = itemRenderer;
        this.loadingIndicator = this.createLoadingIndicator();
        this.pagination = new PaginationClient({
            ...options,
            onItemsLoaded: this.onItemsLoaded.bind(this),
            onError: this.onError.bind(this),
            onLoadingStateChange: this.onLoadingStateChange.bind(this)
        });
        
        this.container.appendChild(this.loadingIndicator);
    }
    
    /**
     * ローディングインジケーターを作成
     */
    createLoadingIndicator() {
        const indicator = document.createElement('div');
        indicator.className = 'pagination-loading d-none text-center py-3';
        indicator.innerHTML = `
            <div class="spinner-border spinner-border-sm" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
            <span class="ms-2">読み込み中...</span>
        `;
        return indicator;
    }
    
    /**
     * アイテム読み込み時の処理
     */
    onItemsLoaded(items, meta) {
        const fragment = document.createDocumentFragment();
        
        items.forEach(item => {
            const element = this.itemRenderer(item);
            if (element) {
                fragment.appendChild(element);
            }
        });
        
        // ローディングインジケーターの前に挿入
        this.container.insertBefore(fragment, this.loadingIndicator);
        
        // 次のページがない場合はローディングインジケーターを隠す
        if (!meta.hasNext) {
            this.loadingIndicator.classList.add('d-none');
            this.showEndMessage();
        }
    }
    
    /**
     * エラー時の処理
     */
    onError(error) {
        console.error('InfiniteScroll error:', error);
        this.showErrorMessage(error.message);
    }
    
    /**
     * ローディング状態変更時の処理
     */
    onLoadingStateChange(loading) {
        if (loading) {
            this.loadingIndicator.classList.remove('d-none');
        } else {
            this.loadingIndicator.classList.add('d-none');
        }
    }
    
    /**
     * 終了メッセージを表示
     */
    showEndMessage() {
        const endMessage = document.createElement('div');
        endMessage.className = 'pagination-end text-center text-muted py-3';
        endMessage.textContent = '以上です';
        this.container.appendChild(endMessage);
    }
    
    /**
     * エラーメッセージを表示
     */
    showErrorMessage(message) {
        const errorMessage = document.createElement('div');
        errorMessage.className = 'pagination-error alert alert-danger mx-3';
        errorMessage.textContent = `読み込みエラー: ${message}`;
        this.container.insertBefore(errorMessage, this.loadingIndicator);
    }
    
    /**
     * 初回読み込み
     */
    async load(params = {}) {
        this.clear();
        return this.pagination.loadFirst(params);
    }
    
    /**
     * コンテンツをクリア
     */
    clear() {
        // アイテム要素のみを削除（ローディングインジケーターは残す）
        Array.from(this.container.children).forEach(child => {
            if (!child.classList.contains('pagination-loading') && 
                !child.classList.contains('pagination-end') &&
                !child.classList.contains('pagination-error')) {
                child.remove();
            }
        });
        
        // エラー・終了メッセージを削除
        this.container.querySelectorAll('.pagination-end, .pagination-error').forEach(el => el.remove());
    }
    
    /**
     * 破棄処理
     */
    destroy() {
        this.pagination.destroy();
        this.container.innerHTML = '';
    }
}

// グローバルに公開
window.PaginationClient = PaginationClient;
window.InfiniteScrollHelper = InfiniteScrollHelper;

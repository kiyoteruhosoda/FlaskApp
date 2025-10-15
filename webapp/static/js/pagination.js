/**
 * 共通ページング機能 - 無限スクロール対応
 * 
 * Familinkアプリケーション用の統一されたページング処理クライアント
 */

class PaginationClient {
    constructor(options = {}) {
        this.baseUrl = options.baseUrl || '';
        this.pageSize = options.pageSize || 200;
        this.autoLoad = options.autoLoad !== false;
        this.loadThreshold = options.loadThreshold || 0.8;
        // 追加のデフォルトパラメータ（初回・以降の読み込み時に常に付与）
        this.defaultParams = options.parameters || {};
        
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
                ...this.defaultParams,
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
                const error = new Error(`HTTP ${response.status}: ${response.statusText}`);
                error.status = response.status;
                error.response = response;
                throw error;
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
                currentPage: this.currentPage - 1,
                // currentPage は次回読み込むページを指しているため、
                // 読み込み直後に 2 であればそれは 1 ページ目の読み込み完了を意味する
                isFirstPage: this.currentPage === 2
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
    constructor(arg1, itemRenderer, options = {}) {
        // 2系コンストラクタ互換: new InfiniteScrollHelper(selectorOrElem, itemRenderer, options)
        // 新API互換: new InfiniteScrollHelper({ paginationClient, container, loadingIndicator, noMoreDataIndicator, threshold })
        this._scrollHandler = null;

        if (typeof arg1 === 'object' && (arg1 !== null) && !('nodeType' in arg1) && !Array.isArray(arg1)) {
            // 新API: optionsオブジェクト受け取り
            const cfg = arg1 || {};

            // container は要素またはセレクタ文字列のどちらでも許可
            if (typeof cfg.container === 'string') {
                this.container = document.querySelector(cfg.container);
            } else if (cfg.container && cfg.container.nodeType === 1) {
                this.container = cfg.container;
            } else {
                this.container = document.body;
            }
            if (!this.container) {
                throw new Error('Container not found for InfiniteScrollHelper');
            }

            // 既存の PaginationClient を利用、なければ作成（最低限の互換）
            if (cfg.paginationClient instanceof PaginationClient) {
                this.pagination = cfg.paginationClient;
            } else {
                this.pagination = new PaginationClient({
                    baseUrl: cfg.baseUrl || '',
                    pageSize: cfg.pageSize || 200,
                    autoLoad: false,
                    parameters: cfg.parameters || {},
                });
            }

            // ローディング/終端インジケータ設定
            this.loadingIndicator = cfg.loadingIndicator || this.createLoadingIndicator();
            this.noMoreDataIndicator = cfg.noMoreDataIndicator || null;
            this.threshold = typeof cfg.threshold === 'number' ? cfg.threshold : 200; // px 単位

            // 既存コールバックをラップしてUI連動
            const prevOnItemsLoaded = this.pagination.onItemsLoaded;
            const prevOnError = this.pagination.onError;

            this.pagination.onItemsLoaded = (items, meta) => {
                // UI: 終端表示制御
                if (this.noMoreDataIndicator) {
                    if (!meta.hasNext) {
                        this.noMoreDataIndicator.style.display = '';
                    } else {
                        this.noMoreDataIndicator.style.display = 'none';
                    }
                }
                if (typeof prevOnItemsLoaded === 'function') {
                    prevOnItemsLoaded(items, meta);
                }
            };

            this.pagination.onLoadingStateChange = (loading) => {
                if (this.loadingIndicator) {
                    this.loadingIndicator.style.display = loading ? '' : 'none';
                }
            };

            this.pagination.onError = (err) => {
                if (typeof prevOnError === 'function') {
                    prevOnError(err);
                } else {
                    this.onError(err);
                }
            };

            // 既存の自動スクロール監視は使わず、こちらで制御
            this.pagination.destroyScrollListener?.();

        } else {
            // 旧API互換: selector + itemRenderer + options
            const containerSelector = arg1;
            this.container = typeof containerSelector === 'string'
                ? document.querySelector(containerSelector)
                : containerSelector;
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
        }

        // 必要ならローディングインジケータをDOMに配置
        if (this.loadingIndicator && !this.loadingIndicator.parentNode) {
            this.container.appendChild(this.loadingIndicator);
        }
        // 初期状態では非表示
        if (this.loadingIndicator) {
            this.loadingIndicator.style.display = 'none';
        }
        if (this.noMoreDataIndicator) {
            this.noMoreDataIndicator.style.display = 'none';
        }
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
        if (!this.loadingIndicator) return;
        if (loading) {
            this.loadingIndicator.classList.remove('d-none');
            this.loadingIndicator.style.display = '';
        } else {
            this.loadingIndicator.classList.add('d-none');
            this.loadingIndicator.style.display = 'none';
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
     * 新API向け: 監視開始 + 初回ロード
     */
    start(params = {}) {
        // スクロールイベント設定
        this.stop();
        const container = this.container === document.body ? document.documentElement : this.container;
        const handler = () => {
            const scrollTop = this.container === document.body ? (window.pageYOffset || document.documentElement.scrollTop) : container.scrollTop;
            const scrollHeight = container.scrollHeight;
            const clientHeight = this.container === document.body ? window.innerHeight : container.clientHeight;
            const distanceFromBottom = scrollHeight - (scrollTop + clientHeight);
            if (distanceFromBottom <= this.threshold && !this.pagination.isLoading && this.pagination.hasNext) {
                this.pagination.loadNext();
            }
        };
        this._scrollHandler = this.pagination.throttle ? this.pagination.throttle(handler, 200) : handler;
        const target = this.container === document.body ? window : this.container;
        target.addEventListener('scroll', this._scrollHandler);

        // 初回ロード
        if (this.noMoreDataIndicator) this.noMoreDataIndicator.style.display = 'none';
        return this.pagination.loadFirst(params);
    }

    /**
     * スクロール監視停止
     */
    stop() {
        const target = this.container === document.body ? window : this.container;
        if (this._scrollHandler) {
            target.removeEventListener('scroll', this._scrollHandler);
            this._scrollHandler = null;
        }
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
        this.stop();
        this.pagination.destroy();
        // 旧API互換: すべてクリア
        if (!this.noMoreDataIndicator && !this.loadingIndicator) {
            this.container.innerHTML = '';
        }
    }
}

// グローバルに公開
window.PaginationClient = PaginationClient;
window.InfiniteScrollHelper = InfiniteScrollHelper;

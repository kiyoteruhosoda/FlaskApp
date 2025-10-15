/**
 * Shared pagination utilities with optional infinite scroll support.
 *
 * Provides a unified pagination client for the Familink application.
 */

function formatMessage(template, params = {}) {
    if (typeof template !== 'string' || !template) {
        return '';
    }
    return template.replace(/%\(([^)]+)\)s/g, (match, key) => {
        if (Object.prototype.hasOwnProperty.call(params, key)) {
            return params[key];
        }
        return '';
    });
}

class PaginationClient {
    constructor(options = {}) {
        this.baseUrl = options.baseUrl || '';
        this.pageSize = options.pageSize || 200;
        this.autoLoad = options.autoLoad !== false;
        this.loadThreshold = options.loadThreshold || 0.8;
        // Additional default parameters appended to every request
        this.defaultParams = options.parameters || {};
        
        // Callback hooks
        this.onItemsLoaded = options.onItemsLoaded || (() => {});
        this.onError = options.onError || ((error) => console.error('Pagination error:', error));
        this.onLoadingStateChange = options.onLoadingStateChange || (() => {});
        
        // Internal state management
        this.isLoading = false;
        this.hasNext = true;
        this.currentCursor = null;
        this.currentPage = 1;
        this.items = [];
        
        // Scroll watcher
        this.scrollContainer = options.scrollContainer || window;
        this.scrollListener = null;
        
        if (this.autoLoad) {
            this.setupScrollListener();
        }
    }
    
    /**
     * Configure scroll listener
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
     * Remove scroll listener
     */
    destroyScrollListener() {
        if (this.scrollListener) {
            this.scrollContainer.removeEventListener('scroll', this.scrollListener);
            this.scrollListener = null;
        }
    }
    
    /**
     * Determine whether additional data should be loaded
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
     * Load the first page
     */
    async loadFirst(params = {}) {
        this.reset();
        return this.loadNext(params);
    }
    
    /**
     * Load the next page
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
            
            // Cursor-based pagination
            if (this.currentCursor) {
                queryParams.cursor = this.currentCursor;
            } else if (!this.currentCursor && this.currentPage > 1) {
                // Offset-based pagination
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
            
            // Normalize response format
            const normalizedData = this.normalizeResponse(data);
            
            // Update state
            this.items.push(...normalizedData.items);
            this.hasNext = normalizedData.hasNext;
            this.currentCursor = normalizedData.nextCursor;
            this.currentPage++;
            
            // Invoke callbacks
            this.onItemsLoaded(normalizedData.items, {
                hasNext: this.hasNext,
                total: normalizedData.totalCount,
                currentPage: this.currentPage - 1,
                // currentPage references the next page that will be loaded, so
                // when it becomes 2 immediately after loading it means the first page finished loading
                isFirstPage: this.currentPage === 2
            });
            
        } catch (error) {
            this.onError(error);
        } finally {
            this.setLoading(false);
        }
    }
    
    /**
     * Reset state
     */
    reset() {
        this.items = [];
        this.currentCursor = null;
        this.currentPage = 1;
        this.hasNext = true;
        this.isLoading = false;
    }
    
    /**
     * Build request URL
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
     * Retrieve authentication headers
     */
    getAuthHeaders() {
        const headers = {};
        
        // CSRF token
        const csrfToken = this.getCsrfToken();
        if (csrfToken) {
            headers['X-CSRFToken'] = csrfToken;
        }
        
        return headers;
    }
    
    /**
     * Read CSRF token
     */
    getCsrfToken() {
        const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : null;
    }
    
    /**
     * Normalize response structure
     */
    normalizeResponse(data) {
        // When items are returned directly
        if (data.items) {
            return {
                items: data.items,
                hasNext: data.hasNext || false,
                nextCursor: data.nextCursor,
                totalCount: data.totalCount
            };
        }
        
        // When the API returns a sessionsList payload
        if (data.sessions) {
            return {
                items: data.sessions,
                hasNext: data.pagination?.hasNext || false,
                nextCursor: data.pagination?.nextCursor,
                totalCount: data.pagination?.totalCount
            };
        }
        
        // When the API returns a selections payload
        if (data.selections) {
            return {
                items: data.selections,
                hasNext: data.pagination?.hasNext || false,
                nextCursor: data.pagination?.nextCursor,
                totalCount: data.pagination?.totalCount
            };
        }
        
        // Fallback for unknown shapes
        return {
            items: [],
            hasNext: false,
            nextCursor: null,
            totalCount: 0
        };
    }
    
    /**
     * Update loading state
     */
    setLoading(loading) {
        this.isLoading = loading;
        this.onLoadingStateChange(loading);
    }
    
    /**
     * Throttle helper
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
     * Teardown
     */
    destroy() {
        this.destroyScrollListener();
        this.reset();
    }
}

/**
 * Helper class for infinite scrolling
 */
class InfiniteScrollHelper {
    constructor(arg1, itemRenderer, options = {}) {
        // Backward-compatible constructor: new InfiniteScrollHelper(selectorOrElem, itemRenderer, options)
        // Compatible constructor for the new API signature
        this._scrollHandler = null;

        if (typeof arg1 === 'object' && (arg1 !== null) && !('nodeType' in arg1) && !Array.isArray(arg1)) {
            // New API: accept an options object
            const cfg = arg1 || {};

            // container may be a DOM element or a selector string
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

            // Use a provided PaginationClient or create a compatible instance
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

            // Configure loading and end-of-list indicators
            this.loadingIndicator = cfg.loadingIndicator || this.createLoadingIndicator();
            this.noMoreDataIndicator = cfg.noMoreDataIndicator || null;
            this.threshold = typeof cfg.threshold === 'number' ? cfg.threshold : 200; // measured in px

            // Wrap existing callbacks to keep UI elements in sync
            const prevOnItemsLoaded = this.pagination.onItemsLoaded;
            const prevOnError = this.pagination.onError;

            this.pagination.onItemsLoaded = (items, meta) => {
                // Toggle end-of-list indicator in the UI
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

            // Replace any existing auto-scroll listener with this implementation
            this.pagination.destroyScrollListener?.();

        } else {
            // Legacy API compatibility: selector + itemRenderer + options
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

        // Append the loading indicator to the DOM when needed
        if (this.loadingIndicator && !this.loadingIndicator.parentNode) {
            this.container.appendChild(this.loadingIndicator);
        }
        // Hide indicators by default
        if (this.loadingIndicator) {
            this.loadingIndicator.style.display = 'none';
        }
        if (this.noMoreDataIndicator) {
            this.noMoreDataIndicator.style.display = 'none';
        }
    }
    
    /**
     * Create a loading indicator element
     */
    createLoadingIndicator() {
        const indicator = document.createElement('div');
        indicator.className = 'pagination-loading d-none text-center py-3';
        const ariaLabel = _('pagination.loading.label', 'Loading...');
        const loadingMessage = _('pagination.loading.message', 'Loading more items...');
        indicator.innerHTML = `
            <div class="spinner-border spinner-border-sm" role="status">
                <span class="visually-hidden">${ariaLabel}</span>
            </div>
            <span class="ms-2">${loadingMessage}</span>
        `;
        return indicator;
    }
    
    /**
     * Handle newly loaded items
     */
    onItemsLoaded(items, meta) {
        const fragment = document.createDocumentFragment();
        
        items.forEach(item => {
            const element = this.itemRenderer(item);
            if (element) {
                fragment.appendChild(element);
            }
        });
        
        // Insert new items before the loading indicator
        this.container.insertBefore(fragment, this.loadingIndicator);
        
        // Hide the loading indicator when there are no more pages
        if (!meta.hasNext) {
            this.loadingIndicator.classList.add('d-none');
            this.showEndMessage();
        }
    }
    
    /**
     * Handle errors
     */
    onError(error) {
        console.error('InfiniteScroll error:', error);
        this.showErrorMessage(error.message);
    }
    
    /**
     * Handle loading state changes
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
     * Display an end-of-list message
     */
    showEndMessage() {
        const endMessage = document.createElement('div');
        endMessage.className = 'pagination-end text-center text-muted py-3';
        endMessage.textContent = _('pagination.end.message', 'No more items to display.');
        this.container.appendChild(endMessage);
    }
    
    /**
     * Display an error message
     */
    showErrorMessage(message) {
        const errorMessage = document.createElement('div');
        errorMessage.className = 'pagination-error alert alert-danger mx-3';
        const template = _('pagination.error.template', 'Load error: %(message)s');
        errorMessage.textContent = formatMessage(template, { message });
        this.container.insertBefore(errorMessage, this.loadingIndicator);
    }
    
    /**
     * Initial load
     */
    async load(params = {}) {
        this.clear();
        return this.pagination.loadFirst(params);
    }

    /**
     * Start observing for the new API and trigger the first load
     */
    start(params = {}) {
        // Register the scroll handler
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

        // Trigger the initial load
        if (this.noMoreDataIndicator) this.noMoreDataIndicator.style.display = 'none';
        return this.pagination.loadFirst(params);
    }

    /**
     * Stop observing scroll events
     */
    stop() {
        const target = this.container === document.body ? window : this.container;
        if (this._scrollHandler) {
            target.removeEventListener('scroll', this._scrollHandler);
            this._scrollHandler = null;
        }
    }
    
    /**
     * Clear rendered content
     */
    clear() {
        // Remove item elements but keep indicators
        Array.from(this.container.children).forEach(child => {
            if (!child.classList.contains('pagination-loading') && 
                !child.classList.contains('pagination-end') &&
                !child.classList.contains('pagination-error')) {
                child.remove();
            }
        });
        
        // Remove error and end-of-list messages
        this.container.querySelectorAll('.pagination-end, .pagination-error').forEach(el => el.remove());
    }
    
    /**
     * Teardown
     */
    destroy() {
        this.stop();
        this.pagination.destroy();
        // Legacy API compatibility: clear everything
        if (!this.noMoreDataIndicator && !this.loadingIndicator) {
            this.container.innerHTML = '';
        }
    }
}

// Expose constructors globally
window.PaginationClient = PaginationClient;
window.InfiniteScrollHelper = InfiniteScrollHelper;

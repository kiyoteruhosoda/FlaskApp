class AlbumSlideshow {
  constructor(options = {}) {
    this.overlayElement = options.overlayElement || null;
    this.stageElement = options.stageElement || null;
    this.imageElement = options.imageElement || null;
    this.titleElement = options.titleElement || null;
    this.metaElement = options.metaElement || null;
    this.counterElement = options.counterElement || null;
    this.emptyStateElement = options.emptyStateElement || null;
    this.loadingElement = options.loadingElement || null;
    this.playPauseButton = options.playPauseButton || null;
    this.prevButton = options.prevButton || null;
    this.nextButton = options.nextButton || null;
    this.closeButton = options.closeButton || null;
    this.intervalMs = Number.isFinite(options.intervalMs) ? Number(options.intervalMs) : 5000;
    this.imageUrlResolver = typeof options.imageUrlResolver === 'function'
      ? options.imageUrlResolver
      : (item) => (item?.fullUrl || item?.thumbnailUrl || '');
    this.metadataFormatter = typeof options.metadataFormatter === 'function'
      ? options.metadataFormatter
      : (item, context) => this.defaultMetadataFormatter(item, context);
    this.labels = {
      play: options.labels?.play || 'Play',
      pause: options.labels?.pause || 'Pause',
      next: options.labels?.next || 'Next',
      previous: options.labels?.previous || 'Previous',
      close: options.labels?.close || 'Close',
      counter: options.labels?.counter || '%(current)s / %(total)s',
      noMedia: options.labels?.noMedia || 'No media items available.',
      shotAt: options.labels?.shotAt || 'Shot at',
      albumTitleFallback: options.labels?.albumTitleFallback || 'Album',
    };

    this.mediaItems = [];
    this.albumTitle = this.labels.albumTitleFallback;
    this.currentIndex = 0;
    this.timerId = null;
    this.isPlaying = false;
    this.isOpen = false;

    this.handleKeydown = this.handleKeydown.bind(this);

    this.bindEvents();
    this.updatePlayButton();
  }

  bindEvents() {
    if (this.playPauseButton) {
      this.playPauseButton.addEventListener('click', (event) => {
        event.preventDefault();
        this.togglePlay();
      });
      this.playPauseButton.setAttribute('type', this.playPauseButton.getAttribute('type') || 'button');
    }

    if (this.prevButton) {
      this.prevButton.addEventListener('click', (event) => {
        event.preventDefault();
        this.showPrevious();
      });
    }

    if (this.nextButton) {
      this.nextButton.addEventListener('click', (event) => {
        event.preventDefault();
        this.showNext();
      });
    }

    if (this.closeButton) {
      this.closeButton.addEventListener('click', (event) => {
        event.preventDefault();
        this.hideOverlay();
      });
    }

    if (this.overlayElement) {
      this.overlayElement.addEventListener('click', (event) => {
        if (event.target === this.overlayElement) {
          this.hideOverlay();
        }
      });
    }
  }

  showOverlay() {
    if (!this.overlayElement || this.isOpen) {
      return;
    }
    this.isOpen = true;
    this.overlayElement.classList.remove('d-none');
    this.overlayElement.setAttribute('aria-hidden', 'false');
    document.body.classList.add('overflow-hidden');
    document.addEventListener('keydown', this.handleKeydown);
  }

  hideOverlay() {
    if (!this.overlayElement || !this.isOpen) {
      return;
    }
    this.stopTimer();
    this.isOpen = false;
    this.overlayElement.classList.add('d-none');
    this.overlayElement.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('overflow-hidden');
    document.removeEventListener('keydown', this.handleKeydown);
  }

  setLoading(isLoading) {
    if (!this.loadingElement) {
      return;
    }
    if (isLoading) {
      this.loadingElement.classList.remove('d-none');
      if (this.stageElement) {
        this.stageElement.classList.add('d-none');
      }
      if (this.emptyStateElement) {
        this.emptyStateElement.classList.add('d-none');
      }
      this.stopTimer();
    } else {
      this.loadingElement.classList.add('d-none');
      if (this.mediaItems.length > 0 && this.stageElement) {
        this.stageElement.classList.remove('d-none');
      }
    }
  }

  load(mediaItems, context = {}) {
    if (Array.isArray(mediaItems)) {
      this.mediaItems = mediaItems.slice();
    } else {
      this.mediaItems = [];
    }
    this.albumTitle = context.albumTitle || this.labels.albumTitleFallback;
    this.currentIndex = 0;
    if (this.titleElement) {
      this.titleElement.textContent = this.albumTitle;
    }
    this.updateView();
  }

  open(startIndex = 0, options = {}) {
    this.showOverlay();
    if (this.loadingElement && !this.loadingElement.classList.contains('d-none')) {
      return;
    }
    if (!this.mediaItems.length) {
      this.showEmptyState();
      return;
    }
    this.currentIndex = this.normalizeIndex(startIndex);
    this.updateView();
    if (options.autoplay === false) {
      this.pause();
    } else {
      this.start();
    }
  }

  normalizeIndex(index) {
    if (!this.mediaItems.length) {
      return 0;
    }
    const total = this.mediaItems.length;
    const normalized = Number(index);
    if (!Number.isFinite(normalized)) {
      return 0;
    }
    if (normalized < 0) {
      const remainder = Math.abs(normalized) % total;
      return remainder === 0 ? 0 : total - remainder;
    }
    return normalized % total;
  }

  start() {
    if (!this.mediaItems.length) {
      this.pause();
      return;
    }
    this.stopTimer();
    this.isPlaying = true;
    this.updatePlayButton();
    this.timerId = window.setInterval(() => this.showNext(), this.intervalMs);
  }

  pause() {
    this.stopTimer();
    this.isPlaying = false;
    this.updatePlayButton();
  }

  stopTimer() {
    if (this.timerId) {
      window.clearInterval(this.timerId);
      this.timerId = null;
    }
  }

  togglePlay() {
    if (!this.mediaItems.length) {
      this.showEmptyState();
      return;
    }
    if (this.isPlaying) {
      this.pause();
    } else {
      this.start();
    }
  }

  showNext() {
    if (!this.mediaItems.length) {
      return;
    }
    this.currentIndex = (this.currentIndex + 1) % this.mediaItems.length;
    this.updateView();
  }

  showPrevious() {
    if (!this.mediaItems.length) {
      return;
    }
    this.currentIndex = (this.currentIndex - 1 + this.mediaItems.length) % this.mediaItems.length;
    this.updateView();
  }

  showEmptyState() {
    if (this.stageElement) {
      this.stageElement.classList.add('d-none');
    }
    if (this.emptyStateElement) {
      this.emptyStateElement.textContent = this.labels.noMedia;
      this.emptyStateElement.classList.remove('d-none');
    }
    if (this.counterElement) {
      this.counterElement.textContent = this.labels.counter
        .replace('%(current)s', '0')
        .replace('%(total)s', '0');
    }
    if (this.metaElement) {
      this.metaElement.textContent = '';
    }
    this.pause();
  }

  updateView() {
    if (!this.mediaItems.length) {
      this.showEmptyState();
      return;
    }

    if (this.emptyStateElement) {
      this.emptyStateElement.classList.add('d-none');
    }
    if (this.stageElement) {
      this.stageElement.classList.remove('d-none');
    }

    const item = this.mediaItems[this.currentIndex];
    const imageUrl = this.imageUrlResolver(item) || '';
    if (this.imageElement) {
      if (imageUrl) {
        this.imageElement.src = imageUrl;
      }
      const altText = this.buildAltText(item);
      if (altText) {
        this.imageElement.alt = altText;
      }
    }

    if (this.counterElement) {
      this.counterElement.textContent = this.labels.counter
        .replace('%(current)s', (this.currentIndex + 1).toString())
        .replace('%(total)s', this.mediaItems.length.toString());
    }

    if (this.metaElement) {
      const context = {
        index: this.currentIndex,
        total: this.mediaItems.length,
        albumTitle: this.albumTitle,
      };
      this.metaElement.textContent = this.metadataFormatter(item, context) || '';
    }

    if (this.titleElement) {
      this.titleElement.textContent = this.albumTitle;
    }
  }

  buildAltText(item) {
    if (!item) {
      return this.albumTitle;
    }
    if (item.filename) {
      return item.filename;
    }
    if (item.title) {
      return item.title;
    }
    return this.albumTitle;
  }

  defaultMetadataFormatter(item, context) {
    const parts = [];
    if (item?.shotAt) {
      const formatted = this.formatDateTime(item.shotAt);
      if (formatted) {
        parts.push(`${this.labels.shotAt}: ${formatted}`);
      }
    }
    parts.push(
      this.labels.counter
        .replace('%(current)s', (context.index + 1).toString())
        .replace('%(total)s', context.total.toString()),
    );
    return parts.join(' · ');
  }

  formatDateTime(value) {
    if (!value) {
      return '';
    }
    const helper = window.appTime;
    if (helper && typeof helper.formatDateTime === 'function') {
      try {
        const formatted = helper.formatDateTime(value, { dateStyle: 'medium', timeStyle: 'short' });
        if (formatted) {
          return formatted;
        }
      } catch (error) {
        console.warn('AlbumSlideshow: appTime formatting failed', error);
      }
    }
    try {
      const date = new Date(value);
      if (!Number.isNaN(date.getTime())) {
        return date.toLocaleString();
      }
    } catch (error) {
      console.warn('AlbumSlideshow: Date formatting failed', error);
    }
    return '';
  }

  updatePlayButton() {
    if (!this.playPauseButton) {
      return;
    }
    const icon = this.playPauseButton.querySelector('i');
    const label = this.playPauseButton.querySelector('[data-label]');
    const text = this.isPlaying ? this.labels.pause : this.labels.play;
    const iconClass = this.isPlaying ? 'bi bi-pause-fill me-1' : 'bi bi-play-fill me-1';
    if (icon) {
      icon.className = iconClass;
    } else {
      this.playPauseButton.insertAdjacentHTML('afterbegin', `<i class="${iconClass}"></i>`);
    }
    if (label) {
      label.textContent = text;
    } else {
      this.playPauseButton.textContent = text;
    }
    this.playPauseButton.setAttribute('aria-label', text);
    this.playPauseButton.setAttribute('title', text);
  }

  handleKeydown(event) {
    if (!this.isOpen) {
      return;
    }
    if (event.key === 'Escape') {
      event.preventDefault();
      this.hideOverlay();
    } else if (event.key === 'ArrowRight') {
      event.preventDefault();
      this.showNext();
    } else if (event.key === 'ArrowLeft') {
      event.preventDefault();
      this.showPrevious();
    } else if (event.key === ' ') {
      event.preventDefault();
      this.togglePlay();
    }
  }
}

window.AlbumSlideshow = AlbumSlideshow;

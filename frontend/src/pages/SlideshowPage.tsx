import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Button, Spinner } from 'react-bootstrap';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../services/api';
import { AlbumDetail, AlbumMediaItem } from '../types/api';

const SlideshowPage: React.FC = () => {
  const { t } = useTranslation();
  const { albumId } = useParams<{ albumId: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const [album, setAlbum] = useState<AlbumDetail | null>(null);
  const [currentIndex, setCurrentIndex] = useState(() => {
    const start = searchParams.get('start');
    return start ? parseInt(start, 10) : 0;
  });
  const [isLoading, setIsLoading] = useState(true);
  // 現在表示中のサムネイル URL（次の画像が用意できるまでクリアしない）
  const [thumbUrl, setThumbUrl] = useState<string | null>(null);
  // 次の画像を読み込み中かどうか（オーバーレイスピナー用）
  const [isImageLoading, setIsImageLoading] = useState(false);
  const [isAutoplay, setIsAutoplay] = useState(() => {
    const autoplay = searchParams.get('autoplay');
    return autoplay !== '0' && autoplay !== 'false' && autoplay !== 'no';
  });
  const [showControls, setShowControls] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const controlsTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const autoplayTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // 署名済み URL のキャッシュ（media.id → URL）
  const urlCacheRef = useRef<Map<number, string>>(new Map());

  const media = album?.media ?? [];
  const currentItem: AlbumMediaItem | undefined = media[currentIndex];

  useEffect(() => {
    if (!albumId) return;
    apiClient
      .getAlbumDetail(parseInt(albumId, 10))
      .then(({ album: a }) => setAlbum(a))
      .catch(() => {})
      .finally(() => setIsLoading(false));
  }, [albumId]);

  /** 署名済み URL を取得する（キャッシュ優先）。 */
  const getThumbUrl = useCallback(async (item: AlbumMediaItem): Promise<string | null> => {
    if (urlCacheRef.current.has(item.id)) {
      return urlCacheRef.current.get(item.id)!;
    }
    const url = await apiClient.getPhotoThumbUrl(item.id, 2048);
    const finalUrl = url || item.thumbnailUrl || null;
    if (finalUrl) {
      urlCacheRef.current.set(item.id, finalUrl);
    }
    return finalUrl;
  }, []);

  /**
   * 現在のアイテムが変わったとき、次の画像が用意できてから表示を切り替える。
   * 準備が整うまで前の画像を表示し続け、オーバーレイスピナーで待機を示す。
   */
  useEffect(() => {
    if (!currentItem) return;
    let cancelled = false;
    setIsImageLoading(true);

    getThumbUrl(currentItem).then((url) => {
      if (cancelled || !url) {
        if (!cancelled) setIsImageLoading(false);
        return;
      }
      // 画像データを実際にブラウザにロードしてから切り替える
      const img = new window.Image();
      img.onload = () => {
        if (cancelled) return;
        setThumbUrl(url);
        setIsImageLoading(false);
      };
      img.onerror = () => {
        if (cancelled) return;
        // エラーでも URL は表示する（ブラウザのデフォルト broken 表示）
        setThumbUrl(url);
        setIsImageLoading(false);
      };
      img.src = url;
    });

    return () => { cancelled = true; };
  }, [currentItem, getThumbUrl]);

  /** 次の画像（+1）をバックグラウンドでプリロードする。 */
  useEffect(() => {
    if (!currentItem || media.length <= 1) return;
    const nextIndex = (currentIndex + 1) % media.length;
    const nextItem = media[nextIndex];
    if (!nextItem || urlCacheRef.current.has(nextItem.id)) return;

    let cancelled = false;
    getThumbUrl(nextItem).then((url) => {
      if (cancelled || !url) return;
      // キャッシュ登録済みなので画像オブジェクトのプリロードのみ
      const img = new window.Image();
      img.src = url;
    });

    return () => { cancelled = true; };
  }, [currentIndex, media, currentItem, getThumbUrl]);

  const goNext = useCallback(() => {
    setCurrentIndex((i) => (i + 1) % media.length);
  }, [media.length]);

  const goPrev = useCallback(() => {
    setCurrentIndex((i) => (i - 1 + media.length) % media.length);
  }, [media.length]);

  useEffect(() => {
    if (!isAutoplay || media.length === 0) return;
    autoplayTimer.current = setInterval(goNext, 4000);
    return () => {
      if (autoplayTimer.current) clearInterval(autoplayTimer.current);
    };
  }, [isAutoplay, goNext, media.length]);

  // 全画面表示の切り替え（ダブルクリック／右下のアイコン）。
  const toggleFullscreen = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => {});
    } else {
      el.requestFullscreen().catch(() => {});
    }
  }, []);

  useEffect(() => {
    const onChange = () => setIsFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener('fullscreenchange', onChange);
    return () => document.removeEventListener('fullscreenchange', onChange);
  }, []);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight' || e.key === ' ') goNext();
      if (e.key === 'ArrowLeft') goPrev();
      if (e.key === 'Escape') {
        // 全画面中の Escape はブラウザが全画面解除するだけに留め、
        // アルバムへは戻らない。
        if (document.fullscreenElement) return;
        navigate(`/albums/${albumId}`);
      }
      if (e.key === 'f' || e.key === 'F') toggleFullscreen();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [goNext, goPrev, navigate, albumId, toggleFullscreen]);

  const handleMouseMove = () => {
    setShowControls(true);
    if (controlsTimer.current) clearTimeout(controlsTimer.current);
    controlsTimer.current = setTimeout(() => setShowControls(false), 3000);
  };

  if (isLoading) {
    return (
      <div className="d-flex justify-content-center align-items-center vh-100 bg-black">
        <Spinner animation="border" variant="light" />
      </div>
    );
  }

  if (!album || media.length === 0) {
    return (
      <div className="d-flex flex-column justify-content-center align-items-center vh-100 bg-black text-white">
        <p>{t('No photos in this album')}</p>
        <Button variant="outline-light" onClick={() => navigate(`/albums/${albumId}`)}>
          {t('Back to Album')}
        </Button>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="d-flex flex-column vh-100 bg-black position-relative"
      onMouseMove={handleMouseMove}
      onDoubleClick={toggleFullscreen}
      data-testid="slideshow-page"
      style={{ cursor: showControls ? 'default' : 'none' }}
    >
      {/* Main image */}
      <div className="flex-grow-1 d-flex justify-content-center align-items-center overflow-hidden position-relative">
        {thumbUrl ? (
          <img
            src={thumbUrl}
            alt={currentItem?.filename ?? ''}
            style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }}
            data-testid="slideshow-image"
          />
        ) : (
          <Spinner animation="border" variant="light" />
        )}
        {/* 次の画像を待機中のオーバーレイスピナー（現在画像を隠さない） */}
        {isImageLoading && thumbUrl && (
          <div
            className="position-absolute d-flex align-items-center justify-content-center"
            style={{
              inset: 0,
              background: 'rgba(0,0,0,0.35)',
              pointerEvents: 'none',
            }}
            data-testid="slideshow-loading-overlay"
          >
            <Spinner animation="border" variant="light" size="sm" />
          </div>
        )}
      </div>

      {/* Controls overlay（全画面表示中はアルバム名などを隠す） */}
      {!isFullscreen && (
      <div
        className="position-absolute w-100"
        style={{
          top: 0,
          left: 0,
          background: 'linear-gradient(to bottom, rgba(0,0,0,0.6), transparent)',
          padding: '1rem',
          opacity: showControls ? 1 : 0,
          transition: 'opacity 0.3s',
          pointerEvents: showControls ? 'auto' : 'none',
        }}
        data-testid="slideshow-controls"
      >
        <div className="d-flex justify-content-between align-items-center text-white">
          <div>
            <Button variant="link" className="text-white p-0 me-3" onClick={() => navigate(`/albums/${albumId}`)}>
              <i className="fa-solid fa-xmark fs-5" />
            </Button>
            <span className="fw-semibold">{album.title}</span>
          </div>
          <div className="d-flex align-items-center gap-3">
            <span className="small">{currentIndex + 1} / {media.length}</span>
            <Button
              variant={isAutoplay ? 'light' : 'outline-light'}
              size="sm"
              onClick={() => setIsAutoplay((v) => !v)}
              data-testid="slideshow-autoplay"
            >
              <i className={`fa-solid ${isAutoplay ? 'fa-pause' : 'fa-play'}`} />
            </Button>
          </div>
        </div>
      </div>
      )}

      {/* Prev / Next buttons */}
      <Button
        variant="link"
        className="position-absolute top-50 start-0 translate-middle-y text-white"
        style={{ opacity: showControls ? 0.8 : 0, transition: 'opacity 0.3s', fontSize: '2rem' }}
        onClick={goPrev}
        data-testid="slideshow-prev"
      >
        <i className="fa-solid fa-chevron-left" />
      </Button>
      <Button
        variant="link"
        className="position-absolute top-50 end-0 translate-middle-y text-white"
        style={{ opacity: showControls ? 0.8 : 0, transition: 'opacity 0.3s', fontSize: '2rem' }}
        onClick={goNext}
        data-testid="slideshow-next"
      >
        <i className="fa-solid fa-chevron-right" />
      </Button>

      {/* Bottom caption */}
      <div
        className="position-absolute w-100 text-center text-white small"
        style={{
          bottom: '1rem',
          opacity: showControls ? 0.8 : 0,
          transition: 'opacity 0.3s',
        }}
      >
        {currentItem?.filename}
      </div>

      {/* Fullscreen toggle（右下） */}
      <Button
        variant="link"
        className="position-absolute text-white p-2"
        style={{
          bottom: '0.5rem',
          right: '0.75rem',
          opacity: showControls ? 0.8 : 0,
          transition: 'opacity 0.3s',
          pointerEvents: showControls ? 'auto' : 'none',
          fontSize: '1.25rem',
        }}
        onClick={(e) => { e.stopPropagation(); toggleFullscreen(); }}
        title={isFullscreen ? t('Exit full screen') : t('Full screen')}
        aria-label={isFullscreen ? t('Exit full screen') : t('Full screen')}
        data-testid="slideshow-fullscreen"
      >
        <i className={`fa-solid ${isFullscreen ? 'fa-compress' : 'fa-expand'}`} />
      </Button>
    </div>
  );
};

export default SlideshowPage;

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Button, Spinner } from 'react-bootstrap';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../services/api';
import { AlbumDetail, AlbumMediaItem } from '../types/api';

/** 1枚先読みする枚数 */
const PRELOAD_AHEAD = 3;
/** スライドショー間隔のデフォルト値（秒） */
const DEFAULT_INTERVAL_SEC = 5;

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
  // ユーザー設定の表示間隔（秒）
  const [slideshowInterval, setSlideshowInterval] = useState(DEFAULT_INTERVAL_SEC);

  const controlsTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // 署名済み URL のキャッシュ（media.id → URL）
  const urlCacheRef = useRef<Map<number, string>>(new Map());
  // 各インデックスの画像が実際にロード済みかどうか（media.id → boolean）
  const imgReadyRef = useRef<Map<number, boolean>>(new Map());

  // 自動再生タイマー管理（ref で制御することで state 更新なしに扱う）
  // timerFiredRef: 最低表示時間タイマーが発火済みか
  // nextReadyRef: 次の画像がロード済みか
  const timerFiredRef = useRef(false);
  const advancePendingRef = useRef(false); // タイマー発火後、次画像待ちかどうか
  const autoplayCleanupRef = useRef<(() => void) | null>(null);

  const media = album?.media ?? [];
  const currentItem: AlbumMediaItem | undefined = media[currentIndex];

  // ユーザー設定の取得
  useEffect(() => {
    apiClient.getUserPreferences().then(({ preferences }) => {
      const v = preferences.slideshow_interval;
      if (typeof v === 'number' && v > 0) setSlideshowInterval(v);
    }).catch(() => {});
  }, []);

  // アルバムデータ取得
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
   * 画像を取得してブラウザにプリロードする。
   * ロード完了時に imgReadyRef を更新し、コールバックを呼ぶ。
   */
  const preloadImage = useCallback(
    (item: AlbumMediaItem, onReady?: () => void): (() => void) => {
      if (imgReadyRef.current.get(item.id)) {
        onReady?.();
        return () => {};
      }
      let cancelled = false;
      getThumbUrl(item).then((url) => {
        if (cancelled || !url) return;
        const img = new window.Image();
        img.onload = () => {
          if (cancelled) return;
          imgReadyRef.current.set(item.id, true);
          onReady?.();
        };
        img.onerror = () => {
          if (cancelled) return;
          // エラーでも「ロード完了」扱いにしてスタックを防ぐ
          imgReadyRef.current.set(item.id, true);
          onReady?.();
        };
        img.src = url;
      });
      return () => { cancelled = true; };
    },
    [getThumbUrl],
  );

  const goNext = useCallback(() => {
    setCurrentIndex((i) => (i + 1) % media.length);
  }, [media.length]);

  const goPrev = useCallback(() => {
    setCurrentIndex((i) => (i - 1 + media.length) % media.length);
  }, [media.length]);

  /**
   * 現在のアイテムが変わったとき：
   * 1. 次の画像が用意できてから thumbUrl を切り替える（現在画像を保持）
   * 2. 3枚先までバックグラウンドプリロード
   * 3. 自動再生タイマーをリセット
   */
  useEffect(() => {
    if (!currentItem) return;

    // 前のクリーンアップを実行
    autoplayCleanupRef.current?.();
    autoplayCleanupRef.current = null;
    timerFiredRef.current = false;
    advancePendingRef.current = false;

    let cancelled = false;
    setIsImageLoading(true);

    // --- 現在画像のロード（ロード後に thumbUrl を切り替える） ---
    const cancelCurrent = preloadImage(currentItem, () => {
      if (cancelled) return;
      getThumbUrl(currentItem).then((url) => {
        if (cancelled || !url) return;
        setThumbUrl(url);
        setIsImageLoading(false);
      });
    });

    // --- 自動再生タイマー ---
    let advanceTimer: ReturnType<typeof setTimeout> | null = null;

    const tryAdvance = () => {
      if (!isAutoplay || media.length <= 1) return;
      goNext();
    };

    if (isAutoplay && media.length > 1) {
      advanceTimer = setTimeout(() => {
        if (cancelled) return;
        timerFiredRef.current = true;
        const nextItem = media[(currentIndex + 1) % media.length];
        if (nextItem && imgReadyRef.current.get(nextItem.id)) {
          // 次の画像がすでにロード済み → すぐ進む
          tryAdvance();
        } else {
          // 次の画像がまだ → ロード完了コールバックで進む
          advancePendingRef.current = true;
        }
      }, slideshowInterval * 1000);
    }

    // --- 3枚先プリロード（+1, +2, +3）---
    const cancelPreloads: Array<() => void> = [];
    for (let offset = 1; offset <= PRELOAD_AHEAD; offset++) {
      const idx = (currentIndex + offset) % media.length;
      const item = media[idx];
      if (!item) continue;

      const onReady = offset === 1
        ? () => {
            // +1 がロード完了 → タイマーが発火済みなら進む
            if (advancePendingRef.current && !cancelled) {
              advancePendingRef.current = false;
              tryAdvance();
            }
          }
        : undefined;

      cancelPreloads.push(preloadImage(item, onReady));
    }

    autoplayCleanupRef.current = () => {
      if (advanceTimer) clearTimeout(advanceTimer);
      cancelPreloads.forEach((fn) => fn());
    };

    return () => {
      cancelled = true;
      if (advanceTimer) clearTimeout(advanceTimer);
      cancelPreloads.forEach((fn) => fn());
      cancelCurrent();
    };
    // isAutoplay / slideshowInterval が変わった場合もリセットしたいので依存に含める
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentItem, isAutoplay, slideshowInterval, media, preloadImage, getThumbUrl, goNext]);

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

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
  const [thumbUrl, setThumbUrl] = useState<string | null>(null);
  const [isAutoplay, setIsAutoplay] = useState(() => {
    const autoplay = searchParams.get('autoplay');
    return autoplay !== '0' && autoplay !== 'false' && autoplay !== 'no';
  });
  const [showControls, setShowControls] = useState(true);
  const controlsTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const autoplayTimer = useRef<ReturnType<typeof setInterval> | null>(null);

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

  useEffect(() => {
    if (!currentItem) return;
    setThumbUrl(null);
    apiClient.getPhotoThumbUrl(currentItem.id, 2048).then((url) => {
      if (url) setThumbUrl(url);
      else if (currentItem.thumbnailUrl) setThumbUrl(currentItem.thumbnailUrl);
    });
  }, [currentItem]);

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

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight' || e.key === ' ') goNext();
      if (e.key === 'ArrowLeft') goPrev();
      if (e.key === 'Escape') navigate(`/albums/${albumId}`);
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [goNext, goPrev, navigate, albumId]);

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
      className="d-flex flex-column vh-100 bg-black position-relative"
      onMouseMove={handleMouseMove}
      data-testid="slideshow-page"
      style={{ cursor: showControls ? 'default' : 'none' }}
    >
      {/* Main image */}
      <div className="flex-grow-1 d-flex justify-content-center align-items-center overflow-hidden">
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
      </div>

      {/* Controls overlay */}
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
    </div>
  );
};

export default SlideshowPage;

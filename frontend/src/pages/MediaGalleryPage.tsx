import React, { useEffect, useState, useCallback } from 'react';
import { Container, Row, Col, Card, Button, Modal, Form, Spinner, Alert } from 'react-bootstrap';
import { useDispatch, useSelector } from 'react-redux';
import { RootState, AppDispatch } from '../store';
import { fetchMediaList } from '../store/mediaSlice';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../services/api';

const MediaGalleryPage: React.FC = () => {
  const { t } = useTranslation();
  const dispatch = useDispatch<AppDispatch>();
  const { mediaList, pagination, isLoading, error } = useSelector((state: RootState) => state.media);

  const [selectedMedia, setSelectedMedia] = useState<any>(null);
  const [showModal, setShowModal] = useState(false);
  const [mediaUrls, setMediaUrls] = useState<{ [key: string]: string }>({});
  const [filter, setFilter] = useState<{
    media_type: '' | 'photo' | 'video';
    sort: string;
  }>({
    media_type: '',
    sort: 'created_at-desc',
  });

  const loadMediaList = useCallback(() => {
    const params: {
      page: number;
      pageSize: number;
      session_id?: string;
      media_type?: 'photo' | 'video';
      sort?: string;
    } = {
      page: 1,
      pageSize: 24,
      sort: filter.sort,
    };
    
    if (filter.media_type) {
      params.media_type = filter.media_type;
    }

    dispatch(fetchMediaList(params));
  }, [dispatch, filter]);

  useEffect(() => {
    loadMediaList();
  }, [loadMediaList]);

  const handleMediaClick = async (media: any) => {
    setSelectedMedia(media);
    setShowModal(true);

    // サムネイルURLとプレイバックURLを取得
    try {
      const thumbnailResponse = await apiClient.getMediaThumbnailUrl(media.id, 1024);
      if (thumbnailResponse.success && thumbnailResponse.data) {
        setMediaUrls(prev => ({
          ...prev,
          [media.id]: thumbnailResponse.data!.url,
        }));
      }
    } catch (error) {
      console.error('Failed to get media URLs:', error);
    }
  };

  const getThumbnailUrl = async (mediaId: string, size: number = 256): Promise<string> => {
    try {
      const response = await apiClient.getMediaThumbnailUrl(mediaId, size);
      if (response.success && response.data) {
        return response.data.url;
      }
    } catch (error) {
      console.error('Failed to get thumbnail URL:', error);
    }
    return '/placeholder-image.png';
  };

  const MediaCard: React.FC<{ media: any }> = ({ media }) => {
    const [thumbnailUrl, setThumbnailUrl] = useState<string>('/placeholder-image.png');

    useEffect(() => {
      getThumbnailUrl(media.id, 256).then(url => {
        setThumbnailUrl(url);
      });
    }, [media.id]);

    return (
      <Card 
        className="h-100 media-card" 
        style={{ cursor: 'pointer' }}
        onClick={() => handleMediaClick(media)}
      >
        <div className="position-relative">
          <Card.Img
            variant="top"
            src={thumbnailUrl}
            style={{ height: '200px', objectFit: 'cover' }}
            onError={(e) => {
              const target = e.target as HTMLImageElement;
              target.src = '/placeholder-image.png';
            }}
          />
          {media.media_type === 'video' && (
            <div className="position-absolute top-50 start-50 translate-middle">
              <i className="bi bi-play-circle-fill text-white fs-1"></i>
            </div>
          )}
          <div className="position-absolute bottom-0 end-0 m-2">
            <span className="badge bg-dark">
              {media.media_type === 'video' ? (
                <><i className="bi bi-camera-video me-1"></i>{media.duration}s</>
              ) : (
                <><i className="bi bi-image me-1"></i>{media.width}x{media.height}</>
              )}
            </span>
          </div>
        </div>
        <Card.Body>
          <Card.Title className="fs-6 text-truncate">{media.filename}</Card.Title>
          <Card.Text className="small text-muted">
            <div>{new Date(media.created_at).toLocaleDateString()}</div>
            <div>{(media.file_size / 1024 / 1024).toFixed(2)} MB</div>
          </Card.Text>
        </Card.Body>
      </Card>
    );
  };

  const MediaModal: React.FC = () => {
    if (!selectedMedia) return null;

    return (
      <Modal 
        show={showModal} 
        onHide={() => setShowModal(false)} 
        size="lg"
        centered
      >
        <Modal.Header closeButton>
          <Modal.Title>{selectedMedia.filename}</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <div className="text-center mb-3">
            {selectedMedia.media_type === 'video' ? (
              <video 
                controls 
                className="img-fluid"
                style={{ maxHeight: '60vh' }}
                src={mediaUrls[selectedMedia.id]}
              />
            ) : (
              <img 
                src={mediaUrls[selectedMedia.id] || '/placeholder-image.png'}
                alt={selectedMedia.filename}
                className="img-fluid"
                style={{ maxHeight: '60vh' }}
              />
            )}
          </div>
          <Row>
            <Col md={6}>
              <h6>{t('File Information')}</h6>
              <ul className="list-unstyled small">
                <li><strong>{t('Type')}:</strong> {selectedMedia.mime_type}</li>
                <li><strong>{t('Size')}:</strong> {(selectedMedia.file_size / 1024 / 1024).toFixed(2)} MB</li>
                <li><strong>{t('Dimensions')}:</strong> {selectedMedia.width} x {selectedMedia.height}</li>
                {selectedMedia.duration && (
                  <li><strong>{t('Duration')}:</strong> {selectedMedia.duration} seconds</li>
                )}
              </ul>
            </Col>
            <Col md={6}>
              <h6>{t('Dates')}</h6>
              <ul className="list-unstyled small">
                <li><strong>{t('Created')}:</strong> {new Date(selectedMedia.created_at).toLocaleString()}</li>
                <li><strong>{t('Updated')}:</strong> {new Date(selectedMedia.updated_at).toLocaleString()}</li>
              </ul>
            </Col>
          </Row>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setShowModal(false)}>
            {t('Close')}
          </Button>
        </Modal.Footer>
      </Modal>
    );
  };

  return (
    <Container fluid className="py-4">
      <Row className="mb-4">
        <Col>
          <h2>{t('Media Gallery')}</h2>
          <p className="text-muted">{t('Browse your photos and videos')}</p>
        </Col>
      </Row>

      <Row className="mb-4">
        <Col md={4}>
          <Form.Select
            value={filter.media_type}
            onChange={(e) => setFilter(prev => ({ 
              ...prev, 
              media_type: e.target.value as '' | 'photo' | 'video'
            }))}
          >
            <option value="">{t('All Media Types')}</option>
            <option value="photo">{t('Photos Only')}</option>
            <option value="video">{t('Videos Only')}</option>
          </Form.Select>
        </Col>
        <Col md={4}>
          <Form.Select
            value={filter.sort}
            onChange={(e) => setFilter(prev => ({ ...prev, sort: e.target.value }))}
          >
            <option value="created_at-desc">{t('Newest First')}</option>
            <option value="created_at-asc">{t('Oldest First')}</option>
            <option value="filename-asc">{t('Name A-Z')}</option>
            <option value="filename-desc">{t('Name Z-A')}</option>
            <option value="file_size-desc">{t('Largest First')}</option>
          </Form.Select>
        </Col>
        <Col md={4} className="d-flex justify-content-end">
          <Button variant="outline-primary" onClick={loadMediaList}>
            <i className="bi bi-arrow-clockwise me-2"></i>
            {t('Refresh')}
          </Button>
        </Col>
      </Row>

      {error && (
        <Alert variant="danger" className="mb-4">
          {error}
        </Alert>
      )}

      {isLoading ? (
        <div className="text-center py-5">
          <Spinner animation="border" />
          <div className="mt-2">{t('Loading media...')}</div>
        </div>
      ) : (
        <>
          <Row className="g-3">
            {mediaList.map((media) => (
              <Col key={media.id} xs={6} md={4} lg={3} xl={2}>
                <MediaCard media={media} />
              </Col>
            ))}
          </Row>

          {mediaList.length === 0 && (
            <div className="text-center py-5">
              <i className="bi bi-images fs-1 text-muted"></i>
              <h5 className="mt-3 text-muted">{t('No media found')}</h5>
              <p className="text-muted">{t('Upload some photos or videos to get started')}</p>
            </div>
          )}

          {pagination.hasNext && (
            <div className="text-center mt-4">
              <Button variant="outline-primary">
                {t('Load More')}
              </Button>
            </div>
          )}
        </>
      )}

      <MediaModal />
    </Container>
  );
};

export default MediaGalleryPage;
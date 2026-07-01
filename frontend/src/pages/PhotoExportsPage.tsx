import React from 'react';
import { Alert, Container } from 'react-bootstrap';
import { useTranslation } from 'react-i18next';

const PhotoExportsPage: React.FC = () => {
  const { t } = useTranslation();

  return (
    <Container fluid className="py-4" data-testid="photo-exports-page">
      <h1 className="h3 mb-3">{t('Photo Exports')}</h1>
      <Alert variant="info">
        <i className="fa-solid fa-circle-info me-2" />
        {t('Export management is not yet implemented.')}
      </Alert>
    </Container>
  );
};

export default PhotoExportsPage;

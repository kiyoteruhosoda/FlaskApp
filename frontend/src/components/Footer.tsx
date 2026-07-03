import React, { useEffect, useState } from 'react';
import { apiClient } from '../services/api';

const Footer: React.FC = () => {
  const [version, setVersion] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    apiClient
      .getVersion()
      .then((res) => {
        if (mounted) setVersion(res.version);
      })
      .catch(() => {
        if (mounted) setVersion(null);
      });
    return () => {
      mounted = false;
    };
  }, []);

  return (
    <footer className="border-top py-2 text-center bg-light" data-testid="app-footer">
      <small className="text-muted">
        PhotoNest{version ? ` v${version}` : ''}
      </small>
    </footer>
  );
};

export default Footer;

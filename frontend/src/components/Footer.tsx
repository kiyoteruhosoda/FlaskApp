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

  // version.json 生成時点（scripts/generate_version.sh）で既に "v" 接頭辞込みの
  // 文字列（例: "v1a2b3c4"）になっているため、ここで追加の "v" は付けない。
  return (
    <footer className="border-top py-2 text-center bg-white" data-testid="app-footer">
      <small className="text-muted">
        PhotoNest{version ? ` ${version}` : ''}
      </small>
    </footer>
  );
};

export default Footer;

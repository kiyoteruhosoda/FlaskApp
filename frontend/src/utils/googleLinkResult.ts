import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

// OAuth コールバック（/auth/google/callback）が戻り先 URL に付与する
// クエリパラメータ（google_link=ok|error, email, reason）を読み取る。
// SPA は Flask の flash を表示できないため、この仕組みで結果を受け取る。
export interface GoogleLinkResult {
  result: 'ok' | 'error';
  email?: string;
  reason?: string;
}

export function useGoogleLinkResult(): GoogleLinkResult | null {
  const location = useLocation();
  const navigate = useNavigate();
  const [result, setResult] = useState<GoogleLinkResult | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const link = params.get('google_link');
    if (link !== 'ok' && link !== 'error') return;
    setResult({
      result: link,
      email: params.get('email') || undefined,
      reason: params.get('reason') || undefined,
    });
    // 一度読み取ったらリロードで再表示されないよう URL から取り除く
    params.delete('google_link');
    params.delete('email');
    params.delete('reason');
    const search = params.toString();
    navigate(
      { pathname: location.pathname, search: search ? `?${search}` : '' },
      { replace: true }
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return result;
}

// reason コードを利用者向けメッセージの i18n キーへ変換する
export function googleLinkErrorText(reason: string | undefined, t: (key: string) => string): string {
  switch (reason) {
    case 'invalid_state':
      return t('The authorization session expired. Please try again.');
    case 'login_required':
      return t('Please sign in before linking a Google account.');
    case 'token_error':
      return t('Failed to obtain token from Google.');
    case 'email_fetch_failed':
      return t('Failed to fetch email from Google.');
    case 'encryption_key_missing':
      return t('Token encryption key is not configured. Set it in System Settings > Security & Signing.');
    default:
      return t('Failed to link Google account.');
  }
}

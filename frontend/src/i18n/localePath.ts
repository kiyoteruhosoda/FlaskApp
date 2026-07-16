import i18n from './config';

export type SupportedLocale = 'en' | 'ja';

const SUPPORTED_LOCALES = new Set<SupportedLocale>(['en', 'ja']);

export const isSupportedLocale = (value: string | undefined): value is SupportedLocale =>
  value !== undefined && SUPPORTED_LOCALES.has(value as SupportedLocale);

export interface LocaleRoutePolicy {
  readonly locale: SupportedLocale;
  readonly loginPath: string;
}

class EnglishLocaleRoutePolicy implements LocaleRoutePolicy {
  readonly locale = 'en';
  readonly loginPath = '/en/login';
}

class JapaneseLocaleRoutePolicy implements LocaleRoutePolicy {
  readonly locale = 'ja';
  readonly loginPath = '/ja/login';
}

const policies: Record<SupportedLocale, LocaleRoutePolicy> = {
  en: new EnglishLocaleRoutePolicy(),
  ja: new JapaneseLocaleRoutePolicy(),
};

export const localeRoutePolicyOf = (locale: SupportedLocale): LocaleRoutePolicy => policies[locale];

export const extractLocaleFromPathname = (pathname: string): SupportedLocale | undefined => {
  const [, segment] = pathname.split('/');
  return isSupportedLocale(segment) ? segment : undefined;
};

export const getLocalizedLoginPath = (pathname: string = window.location.pathname): string => {
  // Keep legacy URLs such as /login valid. Locale-prefixed URLs are invitation links,
  // not a requirement that every SPA route must carry /ja or /en.
  const locale = extractLocaleFromPathname(pathname);
  return locale ? localeRoutePolicyOf(locale).loginPath : '/login';
};

export const syncLocaleFromPathname = async (pathname: string): Promise<void> => {
  const locale = extractLocaleFromPathname(pathname);
  if (!locale || i18n.language === locale) return;
  await i18n.changeLanguage(locale);
};

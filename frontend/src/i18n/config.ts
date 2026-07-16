import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

// 翻訳リソース
import en from './locales/en.json';
import ja from './locales/ja.json';

const resources = {
  en: { translation: en },
  ja: { translation: ja },
};

// ログイン前のページでも /ja/login のようなロケール付きパス、?lang= クエリパラメータ、
// lang Cookie で言語を切り替えられるようにする。バックエンド (Flask-Babel) と
// 同じ Cookie 名 "lang" を使い、パス/クエリで指定された場合は Cookie にも保存して
// 次回以降に引き継ぐ。既定は英語。
i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    fallbackLng: 'en',
    supportedLngs: ['en', 'ja'],

    detection: {
      order: ['path', 'querystring', 'cookie'],
      lookupFromPathIndex: 0,
      lookupQuerystring: 'lang',
      lookupCookie: 'lang',
      caches: ['cookie'],
      cookieMinutes: 60 * 24 * 30, // 30日
    },

    interpolation: {
      escapeValue: false, // React already escapes values
    },

    react: {
      useSuspense: false,
    },
  });

export default i18n;

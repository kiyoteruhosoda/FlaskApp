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

// ログイン前のページでも ?lang= クエリパラメータ / lang Cookie で言語を切り替え
// られるようにする。バックエンド (Flask-Babel) と同じ Cookie 名 "lang" を使い、
// クエリで指定された場合は Cookie にも保存して次回以降に引き継ぐ。既定は英語。
i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    fallbackLng: 'en',
    supportedLngs: ['en', 'ja'],

    detection: {
      order: ['querystring', 'cookie'],
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

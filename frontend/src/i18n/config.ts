import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

// 翻訳リソース
import en from './locales/en.json';
import ja from './locales/ja.json';

const resources = {
  en: { translation: en },
  ja: { translation: ja },
};

i18n
  .use(initReactI18next)
  .init({
    resources,
    lng: 'ja', // デフォルト言語
    fallbackLng: 'en',
    
    interpolation: {
      escapeValue: false, // React already escapes values
    },
    
    react: {
      useSuspense: false,
    },
  });

export default i18n;
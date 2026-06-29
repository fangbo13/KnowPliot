import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import enCommon from './locales/en/common.json';
import enChat from './locales/en/chat.json';
import enAdmin from './locales/en/admin.json';
import zhCommon from './locales/zh/common.json';
import zhChat from './locales/zh/chat.json';
import zhAdmin from './locales/zh/admin.json';

function getInitialLanguage(): string {
  const saved = localStorage.getItem('ey-language');
  if (saved === 'en' || saved === 'zh') return saved;
  const browser = navigator.language || (navigator as any).userLanguage;
  if (browser.startsWith('zh')) return 'zh';
  return 'en';
}

i18n.use(initReactI18next).init({
  resources: {
    en: { common: enCommon, chat: enChat, admin: enAdmin },
    zh: { common: zhCommon, chat: zhChat, admin: zhAdmin },
  },
  lng: getInitialLanguage(),
  fallbackLng: 'en',
  ns: ['common', 'chat', 'admin'],
  defaultNS: 'common',
  interpolation: { escapeValue: false },
});

// Expose a global language switcher for the UI
(window as any).switchLanguage = (lang: 'en' | 'zh') => {
  i18n.changeLanguage(lang);
  localStorage.setItem('ey-language', lang);
};

export default i18n;

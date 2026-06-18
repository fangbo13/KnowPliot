import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import enCommon from './locales/en/common.json';
import enChat from './locales/en/chat.json';
import enAdmin from './locales/en/admin.json';
import zhCommon from './locales/zh/common.json';
import zhChat from './locales/zh/chat.json';
import zhAdmin from './locales/zh/admin.json';

i18n.use(initReactI18next).init({
  resources: {
    en: { common: enCommon, chat: enChat, admin: enAdmin },
    zh: { common: zhCommon, chat: zhChat, admin: zhAdmin },
  },
  lng: 'en',
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
});

export default i18n;

import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import enTranslations from './en.json';
import arTranslations from './ar.json';

const savedLang = localStorage.getItem('confit_lang') || 'en';

i18n
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: enTranslations },
      ar: { translation: arTranslations }
    },
    lng: savedLang,
    fallbackLng: 'en',
    interpolation: {
      escapeValue: false
    }
  });

// Handle RTL direction updates on HTML root
export const setAppLanguage = (lang: 'en' | 'ar') => {
  i18n.changeLanguage(lang);
  localStorage.setItem('confit_lang', lang);
  const dir = lang === 'ar' ? 'rtl' : 'ltr';
  document.documentElement.setAttribute('dir', dir);
  document.documentElement.setAttribute('lang', lang);
  if (lang === 'ar') {
    document.body.classList.add('font-arabic');
  } else {
    document.body.classList.remove('font-arabic');
  }
};

// Initial sync
setAppLanguage(savedLang as 'en' | 'ar');

export default i18n;

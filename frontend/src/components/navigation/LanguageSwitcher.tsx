import React from 'react';
import { useTranslation } from 'react-i18next';
import { useUIStore } from '../../stores/uiStore';

export const LanguageSwitcher: React.FC<{ className?: string }> = ({ className = '' }) => {
  const { i18n } = useTranslation();
  const { language, setLanguage } = useUIStore();

  const toggleLanguage = () => {
    const nextLang = language === 'en' ? 'ar' : 'en';
    setLanguage(nextLang);
  };

  return (
    <button
      onClick={toggleLanguage}
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-full border border-slate-200 hover:border-[#B8935A] bg-white hover:bg-[#FDF8EE] transition-all text-[#1B1F3B] ${className}`}
      aria-label="Switch Language"
      title={language === 'en' ? 'التبديل إلى العربية' : 'Switch to English'}
    >
      <span className="text-[11px] font-bold text-[#7A5C28]">{language === 'en' ? 'EN' : 'عربي'}</span>
      <span className="text-slate-400 text-[10px]">⇄</span>
      <span className="text-[11px] text-slate-600">{language === 'en' ? 'عربي' : 'EN'}</span>
    </button>
  );
};

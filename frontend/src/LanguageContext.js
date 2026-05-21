import React, { createContext, useContext, useState, useEffect } from 'react';
import { translations } from './translations';

const LanguageContext = createContext();

export const LanguageProvider = ({ children }) => {
  const [language, setLanguage] = useState('en');
  const [direction, setDirection] = useState('ltr');

  useEffect(() => {
    // Detect browser language on first load
    const browserLang = navigator.language.split('-')[0];
    const supportedLangs = ['en', 'fa', 'ps'];
    if (supportedLangs.includes(browserLang)) {
      setLanguage(browserLang);
    }
  }, []);

  useEffect(() => {
    // Update direction and document attributes
    const newDirection = language === 'fa' || language === 'ps' ? 'rtl' : 'ltr';
    setDirection(newDirection);
    document.documentElement.dir = newDirection;
    document.documentElement.lang = language;
    document.body.className = `lang-${language}`;
  }, [language]);

  const t = (key) => {
    return translations[language]?.[key] || key;
  };

  return (
    <LanguageContext.Provider value={{ language, setLanguage, direction, t }}>
      {children}
    </LanguageContext.Provider>
  );
};

export const useLanguage = () => {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error('useLanguage must be used within LanguageProvider');
  }
  return context;
};

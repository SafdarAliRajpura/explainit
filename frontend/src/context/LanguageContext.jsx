import { useState, useCallback } from 'react';
import { SUPPORTED_LANGUAGES } from '../config/languages';
import { UI_TRANSLATIONS } from '../config/translations';
import { LanguageContext } from './languageContextInstance';

export function LanguageProvider({ children }) {
  const [activeLang, setActiveLangState] = useState(() => {
    try {
      const savedCode = localStorage.getItem('explainit_active_lang');
      if (savedCode) {
        const found = SUPPORTED_LANGUAGES.find((l) => l.code === savedCode);
        if (found) return found;
      }
    } catch {
      // ignore storage error
    }
    return SUPPORTED_LANGUAGES[0]; // English default
  });

  const [isTranslating, setIsTranslating] = useState(false);

  const setActiveLang = useCallback((lang) => {
    setActiveLangState(lang);
    try {
      if (lang && lang.code) {
        localStorage.setItem('explainit_active_lang', lang.code);
      }
    } catch {
      // ignore storage error
    }
  }, []);

  const t = useCallback(
    (key, params = {}) => {
      const langCode = activeLang?.code || 'en';
      const entry = UI_TRANSLATIONS[key];
      let str = entry?.[langCode] || entry?.en || key;

      if (params && typeof params === 'object') {
        Object.entries(params).forEach(([pKey, pVal]) => {
          str = str.replace(new RegExp(`\\{${pKey}\\}`, 'g'), String(pVal));
        });
      }
      return str;
    },
    [activeLang?.code]
  );

  return (
    <LanguageContext.Provider
      value={{
        activeLang,
        setActiveLang,
        isTranslating,
        setIsTranslating,
        t,
      }}
    >
      {children}
    </LanguageContext.Provider>
  );
}

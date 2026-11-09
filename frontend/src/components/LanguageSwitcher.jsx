import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { SUPPORTED_LANGUAGES } from '../config/languages';

export default function LanguageSwitcher({
  activeLang = SUPPORTED_LANGUAGES[0],
  onSelectLanguage,
  isTranslating = false,
  className = '',
}) {
  const [showMenu, setShowMenu] = useState(false);
  const containerRef = useRef(null);

  // Close dropdown on outside click
  useEffect(() => {
    const handleOutsideClick = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setShowMenu(false);
      }
    };
    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, []);

  const handleSelect = (lang) => {
    setShowMenu(false);
    if (onSelectLanguage) {
      onSelectLanguage(lang);
    }
  };

  return (
    <div ref={containerRef} className={`relative inline-flex items-center ${className}`}>
      {/* Capsule Trigger Button */}
      <button
        onClick={() => setShowMenu((prev) => !prev)}
        disabled={isTranslating}
        className={`flex items-center gap-2 px-3 py-1.5 rounded-full border transition-all duration-300 shadow-sm cursor-pointer ${
          activeLang?.code !== 'en'
            ? 'bg-[#15171A] border-accent/60 text-accent shadow-[0_0_15px_rgba(232,163,61,0.15)]'
            : 'bg-surface border-border-dark hover:border-accent/50 text-text-primary'
        }`}
        title="Switch language (1-Click instant translation & native voice narration)"
      >
        {isTranslating ? (
          <>
            <div className="w-3.5 h-3.5 rounded-full border-2 border-text-muted border-t-accent animate-spin" />
            <span className="text-xs font-medium text-accent">Translating...</span>
          </>
        ) : (
          <>
            <span className="text-sm leading-none">{activeLang?.flag || '🌐'}</span>
            <span className="text-xs font-medium">{activeLang?.nativeName || activeLang?.name || 'English'}</span>
            <svg
              className={`w-3 h-3 text-text-muted transition-transform duration-200 ${
                showMenu ? 'rotate-180 text-accent' : ''
              }`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </>
        )}
      </button>

      {/* Language Selection Dropdown */}
      <AnimatePresence>
        {showMenu && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 5 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 5 }}
            className="absolute right-0 top-10 z-50 w-52 p-2 rounded-2xl bg-[#15171A] border border-border-dark shadow-2xl backdrop-blur-md"
          >
            <div className="text-[10px] uppercase tracking-wider text-text-muted font-bold px-2 py-1 border-b border-border-dark/50 mb-1 flex items-center justify-between">
              <span>Explain In Language</span>
              <span className="text-[9px] text-accent font-normal">1-Click</span>
            </div>
            <div className="max-h-60 overflow-y-auto space-y-0.5 custom-scrollbar">
              {SUPPORTED_LANGUAGES.map((lang) => (
                <button
                  key={lang.code}
                  onClick={() => handleSelect(lang)}
                  className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg text-xs cursor-pointer transition-colors ${
                    activeLang?.code === lang.code
                      ? 'bg-accent/20 text-accent font-semibold'
                      : 'text-text-muted hover:bg-[#262930] hover:text-text-primary'
                  }`}
                >
                  <span className="flex items-center gap-2">
                    <span className="text-base leading-none">{lang.flag}</span>
                    <span>{lang.nativeName}</span>
                    {lang.code !== 'en' && (
                      <span className="text-[10px] text-text-muted/60">({lang.name})</span>
                    )}
                  </span>
                  {activeLang?.code === lang.code && (
                    <span className="text-accent text-xs font-bold">✓</span>
                  )}
                </button>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

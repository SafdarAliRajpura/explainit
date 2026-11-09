import { useLanguage } from '../hooks/useLanguage';
import { SUPPORTED_LANGUAGES } from '../config/languages';
import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

/**
 * Finds the highest quality native browser voice for the given language code.
 * Prioritizes natural/neural voices and avoids mispronouncing text with an English fallback.
 */
function findBestVoiceForLanguage(langCode) {
  if (typeof window === 'undefined' || !('speechSynthesis' in window)) return null;
  const allVoices = window.speechSynthesis.getVoices();
  if (!allVoices || allVoices.length === 0) return null;

  const targetCode = (langCode || 'en').toLowerCase();
  const langConfig = SUPPORTED_LANGUAGES.find((l) => l.code === targetCode);
  const keywords = langConfig?.voiceKeywords || ['Natural', 'Neural', 'Google'];

  // 1. Filter voices for target language (e.g. 'es', 'es-ES', 'hi-IN', 'fr-FR', etc.)
  const matchingVoices = allVoices.filter((v) => {
    if (!v.lang) return false;
    const normalized = v.lang.toLowerCase().replace('_', '-');
    return normalized.startsWith(targetCode) || normalized.includes(`-${targetCode}`);
  });

  if (matchingVoices.length === 0) {
    // Return null so utterance.lang is used directly without forcing a wrong voice
    return null;
  }

  // 2. Look for preferred natural/neural voices by language keywords
  for (const kw of keywords) {
    const found = matchingVoices.find((v) => v.name.toLowerCase().includes(kw.toLowerCase()));
    if (found) return found;
  }

  // 3. Look for generic high-quality markers
  const naturalVoice = matchingVoices.find((v) =>
    /natural|neural|premium|online/i.test(v.name)
  );
  if (naturalVoice) return naturalVoice;

  // 4. Default to first matching native voice for that language
  return matchingVoices[0];
}

export default function AudioNarrationPlayer({
  panels,
  currentIndex,
  onGoToPanel,
  isSpeaking,
  setIsSpeaking,
  language: propLanguage,
}) {
  const { activeLang: contextLang, isTranslating, t } = useLanguage();
  const language = propLanguage || contextLang;
  const [isPaused, setIsPaused] = useState(false);
  const [playbackRate, setPlaybackRate] = useState(1.0);
  const [autoAdvance, setAutoAdvance] = useState(true);
  const [showSpeedMenu, setShowSpeedMenu] = useState(false);

  const utteranceRef = useRef(null);
  const autoAdvanceTimerRef = useRef(null);
  const playerRef = useRef(null);

  // Close menus on click outside
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (playerRef.current && !playerRef.current.contains(e.target)) {
        setShowSpeedMenu(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Register onvoiceschanged to ensure browser voices are ready
  useEffect(() => {
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) return;
    const loadVoices = () => {
      window.speechSynthesis.getVoices();
    };
    loadVoices();
    window.speechSynthesis.onvoiceschanged = loadVoices;
    return () => {
      window.speechSynthesis.onvoiceschanged = null;
    };
  }, []);

  // Clean text for optimal speech pronunciation
  const cleanSpeechText = (text) => {
    if (!text) return '';
    return text
      .replace(/&amp;/g, 'and')
      .replace(/&lt;/g, 'less than')
      .replace(/&gt;/g, 'greater than')
      .replace(/[*_#`~]/g, '')
      .replace(/\s+/g, ' ')
      .trim();
  };

  // Play speech for the specified panel in the synchronized language
  const playSpeech = (index, forceRate = playbackRate) => {
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) return;

    window.speechSynthesis.cancel();
    if (autoAdvanceTimerRef.current) {
      clearTimeout(autoAdvanceTimerRef.current);
    }

    const panel = panels[index];
    if (!panel || !panel.caption) return;

    const speechText = cleanSpeechText(panel.caption);
    const utterance = new SpeechSynthesisUtterance(speechText);
    utteranceRef.current = utterance;

    utterance.rate = forceRate;
    utterance.pitch = 1.0;

    const langCode = (language?.code || 'en').toLowerCase();
    const langConfig = SUPPORTED_LANGUAGES.find((l) => l.code === langCode);
    const bcp47 = langConfig?.bcp47 || 'en-US';

    // 🌍 Synchronize voice automatically with selected language
    const bestVoice = findBestVoiceForLanguage(langCode);
    if (bestVoice) {
      utterance.voice = bestVoice;
      utterance.lang = bestVoice.lang || bcp47;
    } else {
      utterance.voice = null;
      utterance.lang = bcp47;
    }

    utterance.onstart = () => {
      setIsSpeaking(true);
      setIsPaused(false);
    };

    utterance.onend = () => {
      setIsSpeaking(false);
      setIsPaused(false);

      // Auto-advance to next panel if enabled
      if (autoAdvance && index < panels.length - 1) {
        autoAdvanceTimerRef.current = setTimeout(() => {
          onGoToPanel(index + 1);
        }, 800); // 800ms natural breathing room between panels
      }
    };

    utterance.onerror = (e) => {
      if (e.error !== 'canceled' && e.error !== 'interrupted') {
        console.warn('Speech synthesis error:', e);
      }
      setIsSpeaking(false);
      setIsPaused(false);
    };

    window.speechSynthesis.speak(utterance);
  };

  // React to panel index or language changes when speaking is active
  useEffect(() => {
    // If language is currently fetching comic translation, pause speech until ready
    if (isTranslating && language?.code !== 'en') {
      if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
        window.speechSynthesis.cancel();
      }
      return;
    }

    if (isSpeaking && !isPaused) {
      playSpeech(currentIndex);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentIndex, language?.code, panels[currentIndex]?.caption, isTranslating]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
        window.speechSynthesis.cancel();
      }
      if (autoAdvanceTimerRef.current) {
        clearTimeout(autoAdvanceTimerRef.current);
      }
    };
  }, []);

  // Handlers
  const handleTogglePlay = () => {
    if (!('speechSynthesis' in window)) return;

    if (isSpeaking && !isPaused) {
      window.speechSynthesis.pause();
      setIsPaused(true);
    } else if (isSpeaking && isPaused) {
      window.speechSynthesis.resume();
      setIsPaused(false);
    } else {
      setIsSpeaking(true);
      setIsPaused(false);
      if (!isTranslating) {
        playSpeech(currentIndex);
      }
    }
  };

  const handleStop = () => {
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
    if (autoAdvanceTimerRef.current) {
      clearTimeout(autoAdvanceTimerRef.current);
    }
    setIsSpeaking(false);
    setIsPaused(false);
  };

  const handleRateChange = (newRate) => {
    setPlaybackRate(newRate);
    if (isSpeaking) {
      playSpeech(currentIndex, newRate);
    }
  };

  const hasSpeech = typeof window !== 'undefined' && 'speechSynthesis' in window;
  if (!hasSpeech) return null;

  return (
    <div ref={playerRef} className="relative inline-flex items-center">
      {/* Primary Capsule Player */}
      <motion.div 
        layout
        className={`flex items-center gap-2 px-3 py-1.5 rounded-full border transition-all duration-300 shadow-md ${
          isSpeaking 
            ? 'bg-[#15171A] border-accent/60 shadow-[0_0_20px_rgba(232,163,61,0.2)]' 
            : 'bg-surface border-border-dark hover:border-border-dark/80'
        }`}
      >
        {/* Play / Pause / Start Button */}
        <button
          onClick={handleTogglePlay}
          className={`flex items-center justify-center w-7 h-7 rounded-full cursor-pointer transition-all ${
            isSpeaking && !isPaused
              ? 'bg-accent text-charcoal shadow-[0_0_10px_rgba(232,163,61,0.5)]'
              : 'bg-[#262930] text-accent hover:bg-accent hover:text-charcoal'
          }`}
          title={isSpeaking && !isPaused ? 'Pause narration' : 'Play AI narration'}
        >
          {isSpeaking && !isPaused ? (
            <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
              <path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z"/>
            </svg>
          ) : (
            <svg className="w-3.5 h-3.5 translate-x-0.5" fill="currentColor" viewBox="0 0 24 24">
              <path d="M8 5v14l11-7z"/>
            </svg>
          )}
        </button>

        {/* Animated Sound Wave Equalizer */}
        <div 
          onClick={handleTogglePlay}
          className="flex items-center gap-1 h-4 cursor-pointer px-1"
          title={isSpeaking ? (isPaused ? 'Paused' : 'Playing narration') : 'Click to start narration'}
        >
          {[0, 1, 2, 3].map((barIndex) => (
            <motion.span
              key={barIndex}
              className={`w-0.5 rounded-full ${isSpeaking && !isPaused ? 'bg-accent' : 'bg-text-muted/40'}`}
              animate={
                isSpeaking && !isPaused
                  ? {
                      height: [4, 14, 8, 18, 6][barIndex % 5],
                    }
                  : { height: 4 }
              }
              transition={
                isSpeaking && !isPaused
                  ? {
                      repeat: Infinity,
                      repeatType: "reverse",
                      duration: 0.5 + barIndex * 0.15,
                      ease: "easeInOut",
                    }
                  : { duration: 0.2 }
              }
            />
          ))}
        </div>

        {/* Status Label */}
        <button 
          onClick={handleTogglePlay}
          className="text-xs font-medium cursor-pointer text-text-primary hover:text-accent transition-colors hidden sm:inline-block"
        >
          {isTranslating && language?.code !== 'en'
            ? t('translating')
            : isSpeaking
            ? isPaused
              ? t('paused')
              : `${t('narrating')}...`
            : t('listen')}
        </button>

        {/* Compact Speed Dropdown */}
        <div className="relative border-l border-border-dark/60 pl-2 ml-0.5">
          <button
            onClick={() => setShowSpeedMenu((prev) => !prev)}
            className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] font-semibold text-accent hover:bg-[#262930] cursor-pointer transition-colors"
            title={t('speed')}
          >
            <span>{playbackRate}x</span>
            <svg 
              className={`w-2.5 h-2.5 text-text-muted transition-transform duration-200 ${showSpeedMenu ? 'rotate-180 text-accent' : ''}`} 
              fill="none" 
              stroke="currentColor" 
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M19 9l-7 7-7-7" />
            </svg>
          </button>

          {/* Speed Dropdown Menu Popover */}
          <AnimatePresence>
            {showSpeedMenu && (
              <motion.div
                initial={{ opacity: 0, scale: 0.95, y: 5 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: 5 }}
                className="absolute left-1/2 -translate-x-1/2 top-8 z-40 w-24 p-1.5 rounded-xl bg-[#15171A] border border-border-dark shadow-2xl backdrop-blur-md"
              >
                <div className="text-[9px] uppercase tracking-wider text-text-muted font-bold px-2 py-0.5 border-b border-border-dark/50 mb-1 text-center">
                  {t('speed')}
                </div>
                <div className="space-y-0.5">
                  {[0.75, 1.0, 1.25, 1.5, 2.0].map((rate) => (
                    <button
                      key={rate}
                      onClick={() => {
                        handleRateChange(rate);
                        setShowSpeedMenu(false);
                      }}
                      className={`w-full text-center px-2 py-1 rounded-md text-xs font-semibold cursor-pointer transition-colors ${
                        playbackRate === rate
                          ? 'bg-accent text-charcoal'
                          : 'text-text-muted hover:bg-[#262930] hover:text-text-primary'
                      }`}
                    >
                      {rate}x
                    </button>
                  ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Auto-Advance Story Reel Toggle */}
        <button
          onClick={() => setAutoAdvance((prev) => !prev)}
          className={`flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full border cursor-pointer transition-colors ${
            autoAdvance 
              ? 'border-accent/40 bg-accent/10 text-accent' 
              : 'border-border-dark text-text-muted/60 hover:text-text-muted'
          }`}
          title={autoAdvance ? 'Auto-advance to next panel: ON' : 'Auto-advance: OFF'}
        >
          <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M13 5l7 7-7 7M5 5l7 7-7 7" />
          </svg>
          <span className="hidden md:inline">{t('reel')}</span>
        </button>

        {/* Stop Button when active */}
        {isSpeaking && (
          <button
            onClick={handleStop}
            className="p-1 rounded text-text-muted hover:text-red-400 cursor-pointer transition-colors"
            title="Stop narration"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        )}
      </motion.div>
    </div>
  );
}

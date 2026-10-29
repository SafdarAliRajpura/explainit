import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

export default function AudioNarrationPlayer({
  panels,
  currentIndex,
  onGoToPanel,
  isSpeaking,
  setIsSpeaking,
}) {
  const [isPaused, setIsPaused] = useState(false);
  const [playbackRate, setPlaybackRate] = useState(1.0);
  const [autoAdvance, setAutoAdvance] = useState(true);
  const [availableVoices, setAvailableVoices] = useState([]);
  const [selectedVoiceName, setSelectedVoiceName] = useState('');
  const [showVoiceMenu, setShowVoiceMenu] = useState(false);

  const utteranceRef = useRef(null);
  const autoAdvanceTimerRef = useRef(null);

  // 1. Load system voices and pick best English voice
  useEffect(() => {
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) {
      return;
    }

    const loadVoices = () => {
      const allVoices = window.speechSynthesis.getVoices();
      const englishVoices = allVoices.filter(v => v.lang.startsWith('en'));
      setAvailableVoices(englishVoices.length > 0 ? englishVoices : allVoices);

      if (!selectedVoiceName && englishVoices.length > 0) {
        // Preferred natural-sounding voices in modern OS/browsers
        const preferred = englishVoices.find(v => 
          v.name.includes('Google') || 
          v.name.includes('Natural') || 
          v.name.includes('Samantha') || 
          v.name.includes('Daniel') ||
          v.name.includes('David')
        );
        setSelectedVoiceName(preferred ? preferred.name : englishVoices[0].name);
      }
    };

    loadVoices();
    window.speechSynthesis.onvoiceschanged = loadVoices;

    return () => {
      window.speechSynthesis.onvoiceschanged = null;
    };
  }, [selectedVoiceName]);

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

  // 2. Play speech for the specified panel
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

    if (selectedVoiceName) {
      const voice = availableVoices.find(v => v.name === selectedVoiceName);
      if (voice) utterance.voice = voice;
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
      // Speech cancellation emits 'canceled', ignore as normal lifecycle
      if (e.error !== 'canceled' && e.error !== 'interrupted') {
        console.warn('Speech synthesis error:', e);
      }
      setIsSpeaking(false);
      setIsPaused(false);
    };

    window.speechSynthesis.speak(utterance);
  };

  // 3. React to index changes when speaking is active
  useEffect(() => {
    if (isSpeaking && !isPaused) {
      playSpeech(currentIndex);
    }
  }, [currentIndex]);

  // 4. Cleanup on unmount
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
      playSpeech(currentIndex);
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
    <div className="relative inline-flex items-center">
      {/* Primary Capsule Player */}
      <motion.div 
        layout
        className={`flex items-center gap-2.5 px-3 py-1.5 rounded-full border transition-all duration-300 shadow-md ${
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
          {isSpeaking ? (isPaused ? 'Paused' : 'Narrating...') : 'Listen'}
        </button>

        {/* Speed Selector (1x, 1.25x, 1.5x) */}
        <div className="flex items-center border-l border-border-dark/60 pl-2 ml-0.5 gap-1">
          {[1.0, 1.25, 1.5].map((rate) => (
            <button
              key={rate}
              onClick={() => handleRateChange(rate)}
              className={`px-1.5 py-0.5 text-[10px] font-semibold rounded cursor-pointer transition-colors ${
                playbackRate === rate 
                  ? 'bg-accent text-charcoal' 
                  : 'text-text-muted hover:text-text-primary'
              }`}
              title={`Playback speed: ${rate}x`}
            >
              {rate}x
            </button>
          ))}
        </div>

        {/* Auto-Advance Story Reel Toggle */}
        <button
          onClick={() => setAutoAdvance(prev => !prev)}
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
          <span className="hidden md:inline">Reel</span>
        </button>

        {/* Voice Selector Trigger Button */}
        {availableVoices.length > 1 && (
          <div className="relative">
            <button
              onClick={() => setShowVoiceMenu(prev => !prev)}
              className="p-1 rounded text-text-muted hover:text-text-primary cursor-pointer transition-colors"
              title="Select Voice"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
              </svg>
            </button>

            {/* Voice Dropdown Popover */}
            <AnimatePresence>
              {showVoiceMenu && (
                <motion.div
                  initial={{ opacity: 0, scale: 0.95, y: 5 }}
                  animate={{ opacity: 1, scale: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.95, y: 5 }}
                  className="absolute right-0 top-8 z-40 w-56 p-2 rounded-xl bg-[#15171A] border border-border-dark shadow-2xl backdrop-blur-md"
                >
                  <div className="text-[10px] uppercase tracking-wider text-text-muted font-bold px-2 py-1 border-b border-border-dark/50 mb-1">
                    AI Narrator Voice
                  </div>
                  <div className="max-h-48 overflow-y-auto space-y-1">
                    {availableVoices.slice(0, 10).map((voice) => (
                      <button
                        key={voice.name}
                        onClick={() => {
                          setSelectedVoiceName(voice.name);
                          setShowVoiceMenu(false);
                          if (isSpeaking) {
                            playSpeech(currentIndex);
                          }
                        }}
                        className={`w-full text-left px-2 py-1.5 rounded-lg text-xs truncate cursor-pointer transition-colors ${
                          selectedVoiceName === voice.name
                            ? 'bg-accent/20 text-accent font-semibold'
                            : 'text-text-muted hover:bg-[#262930] hover:text-text-primary'
                        }`}
                      >
                        {voice.name.replace(/(Google|Microsoft|Apple|Natural)\s*/gi, '')} ({voice.lang})
                      </button>
                    ))}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}

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

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

const ChevronLeft = () => (
  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="w-5 h-5">
    <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
  </svg>
);

const ChevronRight = () => (
  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="w-5 h-5">
    <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
  </svg>
);

export default function ComicReader({ panels, topic, onReset }) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [direction, setDirection] = useState(1);

  // LinkedIn State
  const [linkedinConnected, setLinkedinConnected] = useState(false);
  const [linkedinName, setLinkedinName] = useState('');
  const [shareStatuses, setShareStatuses] = useState({}); // { [panel_number]: 'idle' | 'posting' | 'success' | 'error' }

  useEffect(() => {
    const checkLinkedinStatus = async () => {
      try {
        const response = await fetch('http://localhost:8000/auth/linkedin/status');
        const data = await response.json();
        if (data.connected) {
          setLinkedinConnected(true);
          setLinkedinName(data.name);
        } else {
          setLinkedinConnected(false);
        }
      } catch (err) {
        console.error('Failed to check LinkedIn status:', err);
      }
    };
    checkLinkedinStatus();
  }, []);

  const handleConnectLinkedin = () => {
    return new Promise((resolve) => {
      const width = 600;
      const height = 700;
      const left = window.screen.width / 2 - width / 2;
      const top = window.screen.height / 2 - height / 2;
      const popup = window.open(
        'http://localhost:8000/auth/linkedin/login',
        'linkedin_login',
        `width=${width},height=${height},top=${top},left=${left}`
      );

      const pollTimer = setInterval(async () => {
        if (popup && popup.closed) {
          clearInterval(pollTimer);
          resolve(false);
        }
        try {
          const response = await fetch('http://localhost:8000/auth/linkedin/status');
          const data = await response.json();
          if (data.connected) {
            setLinkedinConnected(true);
            setLinkedinName(data.name);
            clearInterval(pollTimer);
            if (popup && !popup.closed) popup.close();
            resolve(true);
          }
        } catch (err) {
          // Ignore fetch errors during polling
        }
      }, 2000);
    });
  };

  const handleShare = async (panelNum, caption) => {
    if (!linkedinConnected) {
      const connected = await handleConnectLinkedin();
      if (!connected) return;
    }

    setShareStatuses(prev => ({ ...prev, [panelNum]: 'posting' }));

    try {
      const url = `http://localhost:8000/linkedin/post-panel?panel_number=${panelNum}&caption=${encodeURIComponent(caption)}`;
      const response = await fetch(url, { method: 'POST' });
      const data = await response.json();

      if (response.ok && data.success) {
        setShareStatuses(prev => ({ ...prev, [panelNum]: 'success' }));
        setTimeout(() => {
          setShareStatuses(prev => ({ ...prev, [panelNum]: 'idle' }));
        }, 2500);
      } else {
        console.error("LinkedIn Post Error:", data);
        setShareStatuses(prev => ({ ...prev, [panelNum]: 'error' }));
        setTimeout(() => {
          setShareStatuses(prev => ({ ...prev, [panelNum]: 'idle' }));
        }, 2500);
      }
    } catch (err) {
      console.error("LinkedIn Post Exception:", err);
      setShareStatuses(prev => ({ ...prev, [panelNum]: 'error' }));
      setTimeout(() => {
        setShareStatuses(prev => ({ ...prev, [panelNum]: 'idle' }));
      }, 2500);
    }
  };

  const goToNext = () => {
    if (currentIndex < panels.length - 1) {
      setDirection(1);
      setCurrentIndex(prev => prev + 1);
    }
  };

  const goToPrev = () => {
    if (currentIndex > 0) {
      setDirection(-1);
      setCurrentIndex(prev => prev - 1);
    }
  };

  const goToPanel = (index) => {
    setDirection(index > currentIndex ? 1 : -1);
    setCurrentIndex(index);
  };

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'ArrowRight') goToNext();
      if (e.key === 'ArrowLeft') goToPrev();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [currentIndex, panels.length]);

  const variants = {
    initial: (dir) => ({
      opacity: 0,
      x: dir > 0 ? 40 : -40,
    }),
    animate: {
      opacity: 1,
      x: 0,
      transition: { duration: 0.4, ease: "easeOut" }
    },
    exit: (dir) => ({
      opacity: 0,
      x: dir > 0 ? -40 : 40,
      transition: { duration: 0.3, ease: "easeIn" }
    })
  };

  const currentPanel = panels[currentIndex];

  return (
    <div className="w-full max-w-7xl mx-auto flex flex-col items-center">
      
      {/* Top Header */}
      <div className="w-full flex justify-between items-start mb-8">
        {/* Verified Source Indicator */}
        <div className="inline-flex items-center gap-3 px-1.5 py-1.5 rounded-full border border-border-dark bg-surface shadow-sm">
          <div className="flex items-center gap-2.5 bg-charcoal px-4 py-1.5 rounded-full border border-border-dark/50 shadow-inner">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-50"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-accent shadow-[0_0_8px_rgba(232,163,61,0.8)]"></span>
            </span>
            <span className="text-[10px] tracking-[0.2em] uppercase text-text-primary font-semibold">Verified Source</span>
          </div>
          <span className="text-sm text-text-muted font-light pr-4">
            Topic: <span className="text-text-primary font-medium capitalize ml-1">{topic}</span>
          </span>
        </div>

        {/* LinkedIn Connection Indicator */}
        <div className="flex items-center pt-2">
          {linkedinConnected ? (
            <div className="flex items-center gap-2 text-xs text-text-muted">
              <span className="w-1.5 h-1.5 rounded-full bg-green-500 shadow-[0_0_5px_rgba(34,197,94,0.3)]"></span>
              Connected as {linkedinName}
            </div>
          ) : (
            <button 
              onClick={handleConnectLinkedin}
              className="flex items-center gap-1.5 text-xs text-text-muted hover:text-text-primary transition-colors cursor-pointer"
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4">
                <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>
              </svg>
              Connect LinkedIn
            </button>
          )}
        </div>
      </div>

      <div className="w-full flex flex-col lg:flex-row gap-10 lg:gap-16 items-stretch">
        
        {/* Left Side: Image Container */}
        <div className="w-full lg:w-[55%] relative overflow-hidden rounded-2xl border border-border-dark shadow-2xl bg-surface aspect-square md:aspect-[4/3] flex items-center justify-center shrink-0">
          <AnimatePresence mode="wait" custom={direction}>
            {currentPanel?.image_url ? (
              <motion.div
                key={currentIndex + "img"}
                custom={direction}
                variants={variants}
                initial="initial"
                animate="animate"
                exit="exit"
                className="absolute inset-0 w-full h-full"
              >
                <img 
                  src={currentPanel.image_url}
                  alt={`Panel ${currentIndex + 1}`}
                  className="w-full h-full object-cover contrast-[1.15] saturate-[1.2] brightness-110"
                />
                {/* Cinematic Vignette Overlay */}
                <div className="absolute inset-0 bg-gradient-to-tr from-[#0B0C0E]/40 via-transparent to-[#0B0C0E]/10 pointer-events-none mix-blend-overlay" />
                <div className="absolute inset-0 shadow-[inset_0_0_40px_rgba(11,12,14,0.5)] pointer-events-none" />
              </motion.div>
            ) : (
              <motion.div
                key={currentIndex + "img-fallback"}
                custom={direction}
                variants={variants}
                initial="initial"
                animate="animate"
                exit="exit"
                className="absolute inset-0 flex items-center justify-center"
              >
                <span className="text-text-muted font-medium">No Image</span>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Right Side: Content & Controls */}
        <div className="w-full lg:w-[45%] flex flex-col justify-between py-2 lg:py-6">
          
          {/* Animated Text Content */}
          <div className="flex-1 flex flex-col justify-center">
            <AnimatePresence mode="wait" custom={direction}>
              <motion.div
                key={currentIndex + "txt"}
                custom={direction}
                variants={variants}
                initial="initial"
                animate="animate"
                exit="exit"
                className="w-full max-w-xl"
              >
                <div className="flex items-center justify-between mb-6">
                  <p className="text-accent text-xs tracking-[0.2em] uppercase font-semibold">
                    Panel {currentIndex + 1} of {panels.length}
                  </p>
                  
                  <button 
                    onClick={() => handleShare(currentPanel?.panel_number, currentPanel?.caption)}
                    disabled={shareStatuses[currentPanel?.panel_number] === 'posting'}
                    className="flex items-center gap-1.5 text-xs text-text-muted hover:text-text-primary transition-colors cursor-pointer"
                    title="Share to LinkedIn"
                  >
                    {shareStatuses[currentPanel?.panel_number] === 'posting' && (
                      <div className="w-3 h-3 rounded-full border-2 border-text-muted border-t-accent animate-spin" />
                    )}
                    {shareStatuses[currentPanel?.panel_number] === 'success' && (
                      <span className="text-accent font-medium flex items-center gap-1">
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
                        Posted!
                      </span>
                    )}
                    {shareStatuses[currentPanel?.panel_number] === 'error' && (
                      <span className="text-red-400/80 font-medium">Couldn't post</span>
                    )}
                    {(!shareStatuses[currentPanel?.panel_number] || shareStatuses[currentPanel?.panel_number] === 'idle') && (
                      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M7.217 10.907a2.25 2.25 0 100 2.186m0-2.186c.18.324.283.696.283 1.093s-.103.77-.283 1.093m0-2.186l9.566-5.314m-9.566 7.5l9.566 5.314m0 0a2.25 2.25 0 103.935 2.186 2.25 2.25 0 00-3.935-2.186zm0-12.814a2.25 2.25 0 103.933-2.185 2.25 2.25 0 00-3.933 2.185z" />
                      </svg>
                    )}
                  </button>
                </div>
                <p className="font-fraunces text-2xl md:text-3xl lg:text-4xl text-text-primary leading-[1.4]">
                  {currentPanel?.caption}
                </p>
              </motion.div>
            </AnimatePresence>
          </div>

          {/* Fixed Controls Container */}
          <div className="mt-12 flex flex-col gap-8">
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-3">
                <button 
                  onClick={goToPrev}
                  disabled={currentIndex === 0}
                  className={`p-3 rounded-full border transition-colors ${currentIndex === 0 ? 'border-border-dark/50 text-border-dark cursor-not-allowed' : 'border-border-dark text-text-muted hover:text-text-primary hover:border-text-muted hover:bg-surface cursor-pointer'}`}
                >
                  <ChevronLeft />
                </button>
                <button 
                  onClick={goToNext}
                  disabled={currentIndex === panels.length - 1}
                  className={`p-3 rounded-full border transition-colors ${currentIndex === panels.length - 1 ? 'border-border-dark/50 text-border-dark cursor-not-allowed' : 'border-border-dark text-text-muted hover:text-text-primary hover:border-text-muted hover:bg-surface cursor-pointer'}`}
                >
                  <ChevronRight />
                </button>
              </div>
              
              <div className="h-6 w-[1px] bg-border-dark" />
              
              <div className="flex items-center gap-3">
                {panels.map((_, idx) => (
                  <button
                    key={idx}
                    onClick={() => goToPanel(idx)}
                    className={`w-2.5 h-2.5 rounded-full transition-all cursor-pointer ${
                      idx === currentIndex 
                        ? 'bg-accent scale-125' 
                        : 'bg-transparent border border-border-dark hover:border-text-muted'
                    }`}
                    aria-label={`Go to panel ${idx + 1}`}
                  />
                ))}
              </div>
            </div>

            <div className="pt-8 border-t border-border-dark flex">
              <motion.button 
                onClick={onReset}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                className="group relative flex items-center justify-center gap-2.5 w-full md:w-auto px-8 py-3.5 border border-border-dark bg-surface text-text-muted rounded-xl overflow-hidden cursor-pointer shadow-sm hover:border-accent/40 hover:shadow-[0_0_15px_rgba(232,163,61,0.15)] transition-all duration-300"
              >
                <div className="absolute inset-0 bg-gradient-to-r from-transparent via-accent/5 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-1000 ease-in-out" />
                
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4 text-accent group-hover:rotate-12 transition-transform duration-300">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456zM16.894 20.567L16.5 21.75l-.394-1.183a2.25 2.25 0 00-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 001.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 001.423 1.423l1.183.394-1.183.394a2.25 2.25 0 00-1.423 1.423z" />
                </svg>

                <span className="text-sm font-medium tracking-wide relative z-10 group-hover:text-text-primary transition-colors duration-300">Explain another topic</span>
              </motion.button>
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}

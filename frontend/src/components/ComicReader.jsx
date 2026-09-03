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
      
      {/* Top indicator */}
      <div className="w-full flex justify-start mb-8">
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
                <p className="text-accent text-xs tracking-[0.2em] uppercase mb-6 font-semibold">
                  Panel {currentIndex + 1} of {panels.length}
                </p>
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

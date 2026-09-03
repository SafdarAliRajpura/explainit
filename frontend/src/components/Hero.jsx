import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import ComicReader from './ComicReader';

const LOADING_MESSAGES = [
  "Retrieving grounded facts...",
  "Writing the panel script...",
  "Illustrating panel 1 of 3...",
  "Illustrating panel 2 of 3...",
  "Illustrating panel 3 of 3..."
];

export default function Hero() {
  const [topic, setTopic] = useState('');
  const [status, setStatus] = useState('idle'); // 'idle', 'loading', 'success', 'refused', 'error'
  const [panels, setPanels] = useState([]);
  const [errorMessage, setErrorMessage] = useState('');
  const [loadingIndex, setLoadingIndex] = useState(0);

  // Cycle loading messages
  useEffect(() => {
    let interval;
    if (status === 'loading') {
      interval = setInterval(() => {
        setLoadingIndex((prev) => (prev + 1) % LOADING_MESSAGES.length);
      }, 4500);
    } else {
      setLoadingIndex(0);
    }
    return () => clearInterval(interval);
  }, [status]);

  const handleGenerate = async () => {
    if (!topic.trim()) return;

    setStatus('loading');
    setErrorMessage('');
    setPanels([]);

    try {
      const response = await fetch('http://localhost:8000/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic: topic.trim() })
      });

      if (!response.ok) {
        throw new Error("Server returned an error.");
      }

      const data = await response.json();

      if (data.grounded) {
        setPanels(data.panels || []);
        setStatus('success');
      } else {
        setErrorMessage(data.message || "Could not ground the topic in real sources.");
        setStatus('refused');
      }
    } catch (err) {
      setErrorMessage("Couldn't reach the server. Is the backend running?");
      setStatus('error');
    }
  };

  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.15,
        delayChildren: 0.1,
      },
    },
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: {
      opacity: 1,
      y: 0,
      transition: { duration: 0.6, ease: "easeOut" },
    },
  };

  // 1. IDLE STATE
  const renderIdle = () => (
    <motion.div 
      className="w-full max-w-4xl text-center space-y-6"
      variants={containerVariants}
      initial="hidden"
      animate="visible"
      key="idle"
    >
      <motion.h2 
        className="text-4xl md:text-5xl lg:text-6xl font-fraunces font-medium leading-[1.15] tracking-tight text-text-primary"
        variants={itemVariants}
      >
        Input a topic, get an illustrated comic, backed by real facts.
      </motion.h2>

      <motion.p 
        className="text-lg md:text-xl text-text-muted font-light max-w-2xl mx-auto"
        variants={itemVariants}
      >
        Every fact is traceable to real source material.
      </motion.p>

      <motion.div 
        className="w-full max-w-xl mx-auto pt-10 flex flex-col sm:flex-row gap-4"
        variants={itemVariants}
      >
        <input
          type="text"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          placeholder="Try: How GANs work"
          className="flex-1 bg-surface text-text-primary placeholder-text-muted border border-border-dark rounded-xl px-6 py-4 text-lg focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent focus:shadow-[0_0_15px_rgba(232,163,61,0.2)] transition-all"
        />
        <motion.button
          onClick={handleGenerate}
          whileHover={{ scale: 1.02, filter: "brightness(1.1)" }}
          whileTap={{ scale: 0.98 }}
          className="bg-accent text-charcoal font-medium text-lg px-8 py-4 rounded-xl cursor-pointer transition-colors"
        >
          Generate
        </motion.button>
      </motion.div>
    </motion.div>
  );

  // 2. LOADING STATE
  const renderLoading = () => (
    <motion.div
      key="loading"
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.98 }}
      transition={{ duration: 0.8, ease: "easeOut" }}
      className="w-full max-w-md flex flex-col items-center justify-center space-y-12 py-10"
    >
      {/* Abstract Breathing Rings (AI Thinking) */}
      <div className="relative w-24 h-24 flex items-center justify-center">
        <motion.div 
          className="absolute inset-0 rounded-full border border-accent/20"
          animate={{ scale: [1, 1.5, 1], opacity: [0.5, 0, 0.5] }}
          transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
        />
        <motion.div 
          className="absolute inset-2 rounded-full border border-accent/40"
          animate={{ scale: [1, 1.3, 1], opacity: [0.8, 0.2, 0.8] }}
          transition={{ duration: 3, repeat: Infinity, ease: "easeInOut", delay: 0.5 }}
        />
        <div className="w-3 h-3 rounded-full bg-accent shadow-[0_0_20px_rgba(232,163,61,1)] animate-pulse" />
      </div>

      {/* Cinematic Text Crossfade */}
      <div className="h-12 relative flex flex-col items-center justify-start w-full">
        <AnimatePresence mode="wait">
          <motion.p
            key={loadingIndex}
            initial={{ opacity: 0, y: 10, filter: "blur(4px)" }}
            animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
            exit={{ opacity: 0, y: -10, filter: "blur(4px)" }}
            transition={{ duration: 0.6, ease: "easeOut" }}
            className="text-lg md:text-xl text-text-primary font-fraunces absolute text-center w-full tracking-wide"
          >
            {LOADING_MESSAGES[loadingIndex]}
          </motion.p>
        </AnimatePresence>
      </div>

      {/* Elegant Step Indicators */}
      <div className="flex items-center gap-3">
        {LOADING_MESSAGES.map((_, idx) => (
          <div
            key={idx}
            className={`h-1 rounded-full transition-all duration-1000 ${
              idx === loadingIndex 
                ? 'w-8 bg-accent shadow-[0_0_8px_rgba(232,163,61,0.6)]' 
                : idx < loadingIndex 
                  ? 'w-2 bg-accent/30'
                  : 'w-2 bg-border-dark'
            }`}
          />
        ))}
      </div>
    </motion.div>
  );

  // 3. REFUSED STATE
  const renderRefused = () => (
    <motion.div
      key="refused"
      initial={{ opacity: 0, scale: 0.95, y: 20 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.95, y: -20 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
      className="w-full max-w-2xl relative"
    >
      <div className="absolute inset-0 bg-accent/5 rounded-3xl blur-2xl" />
      <div className="relative flex flex-col items-center text-center p-10 md:p-14 bg-surface border border-border-dark rounded-3xl shadow-xl overflow-hidden">
        {/* Subtle top edge glow */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-3/4 h-px bg-gradient-to-r from-transparent via-accent/30 to-transparent" />
        
        {/* Icon */}
        <div className="mb-8 relative">
          <div className="absolute inset-0 bg-accent/20 rounded-full blur-xl" />
          <div className="relative bg-charcoal p-4 rounded-2xl border border-border-dark text-accent shadow-[0_0_15px_rgba(232,163,61,0.15)]">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-8 h-8">
              <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m3.75 9v6m3-3H9m1.5-12H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
            </svg>
          </div>
        </div>

        <p className="text-accent text-xs font-semibold tracking-[0.2em] uppercase mb-4">Topic Not Grounded</p>
        <p className="text-xl md:text-2xl text-text-primary font-fraunces leading-relaxed max-w-lg mb-10">
          {errorMessage}
        </p>

        <motion.button 
          onClick={() => setStatus('idle')}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          className="group relative flex items-center justify-center gap-3 px-8 py-3.5 border border-border-dark bg-charcoal text-text-muted rounded-xl overflow-hidden cursor-pointer shadow-sm hover:border-text-muted hover:text-text-primary transition-all duration-300"
        >
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4 group-hover:-translate-x-1 transition-transform duration-300">
            <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" />
          </svg>
          <span className="text-sm font-medium tracking-wide relative z-10">Search another topic</span>
        </motion.button>
      </div>
    </motion.div>
  );

  // 4. ERROR STATE
  const renderError = () => (
    <motion.div
      key="error"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      className="w-full max-w-xl text-center space-y-4"
    >
      <p className="text-red-400 text-sm font-semibold tracking-widest uppercase">Connection Error</p>
      <p className="text-lg text-red-200/80 font-light">{errorMessage}</p>
      <button 
        onClick={() => setStatus('idle')}
        className="mt-8 text-sm text-text-primary underline hover:text-red-400 transition-colors cursor-pointer"
      >
        Try again
      </button>
    </motion.div>
  );

  // 5. SUCCESS STATE
  const renderSuccess = () => (
    <motion.div
      key="success"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="w-full max-w-7xl"
    >
      <ComicReader 
        panels={panels} 
        topic={topic} 
        onReset={() => {
          setStatus('idle');
          setTopic('');
          setPanels([]);
        }} 
      />
    </motion.div>
  );

  return (
    <div className="min-h-screen bg-charcoal text-text-primary font-inter flex flex-col">
      {/* Top Bar */}
      <header className="w-full max-w-7xl mx-auto px-4 py-8">
        <h1 className="font-fraunces text-2xl font-medium tracking-wide">ExplainIT</h1>
      </header>

      {/* Main Content */}
      <main className="flex-1 flex flex-col items-center justify-center px-4 pb-24">
        <AnimatePresence mode="wait">
          {status === 'idle' && renderIdle()}
          {status === 'loading' && renderLoading()}
          {status === 'refused' && renderRefused()}
          {status === 'error' && renderError()}
          {status === 'success' && renderSuccess()}
        </AnimatePresence>
      </main>
    </div>
  );
}

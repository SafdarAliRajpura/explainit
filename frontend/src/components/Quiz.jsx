import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

const slideVariants = {
  initial: (dir) => ({ opacity: 0, x: dir > 0 ? 40 : -40 }),
  animate: { opacity: 1, x: 0, transition: { duration: 0.4, ease: 'easeOut' } },
  exit:    (dir) => ({ opacity: 0, x: dir > 0 ? -40 : 40, transition: { duration: 0.3, ease: 'easeIn' } }),
};

function getReactionLine(score, total) {
  const ratio = score / total;
  if (ratio === 1)   return 'Perfect — you\'ve got this.';
  if (ratio >= 0.66) return 'Solid grasp, one gap to close.';
  return 'Worth another pass through the comic.';
}

export default function Quiz({ topic, onBackToComic, onReset }) {
  const [status, setStatus]               = useState('loading');   // 'loading' | 'ready' | 'error'
  const [questions, setQuestions]         = useState([]);
  const [currentIndex, setCurrentIndex]   = useState(0);
  const [direction, setDirection]         = useState(1);
  const [selectedAnswer, setSelectedAnswer] = useState(null);
  const [answered, setAnswered]           = useState(false);
  const [score, setScore]                 = useState(0);
  const [quizComplete, setQuizComplete]   = useState(false);

  useEffect(() => {
    const fetchQuiz = async () => {
      try {
        const res = await fetch('http://localhost:8000/generate-quiz', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ topic }),
        });
        if (!res.ok) throw new Error('Bad response');
        const data = await res.json();
        setQuestions(data.questions || []);
        setStatus('ready');
      } catch {
        setStatus('error');
      }
    };
    fetchQuiz();
  }, [topic]);

  const currentQ = questions[currentIndex];

  const handleSelect = (idx) => {
    if (answered) return;
    setSelectedAnswer(idx);
    setAnswered(true);
    if (idx === currentQ.correct_index) {
      setScore(prev => prev + 1);
    }
  };

  const handleNext = () => {
    const isLast = currentIndex === questions.length - 1;
    if (isLast) {
      setQuizComplete(true);
      return;
    }
    setDirection(1);
    setCurrentIndex(prev => prev + 1);
    setSelectedAnswer(null);
    setAnswered(false);
  };

  // ── LOADING ─────────────────────────────────────────────────────────────────
  if (status === 'loading') {
    return (
      <div className="w-full max-w-2xl mx-auto flex flex-col items-center justify-center py-24 gap-8">
        <motion.div
          className="w-2.5 h-2.5 rounded-full bg-accent"
          animate={{ scale: [1, 1.6, 1], opacity: [1, 0.4, 1] }}
          transition={{ duration: 1.4, repeat: Infinity, ease: 'easeInOut' }}
          style={{ boxShadow: '0 0 16px rgba(232,163,61,0.8)' }}
        />
        <p className="font-fraunces text-xl text-text-primary tracking-wide">
          Preparing your quiz...
        </p>
      </div>
    );
  }

  // ── ERROR ────────────────────────────────────────────────────────────────────
  if (status === 'error') {
    return (
      <motion.div
        initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-2xl mx-auto flex flex-col items-center gap-6 py-24"
      >
        <p className="text-text-muted font-light text-lg">
          Couldn't generate a quiz right now.
        </p>
        <button
          onClick={onBackToComic}
          className="text-sm text-text-muted hover:text-text-primary underline transition-colors cursor-pointer"
        >
          ← Back to comic
        </button>
      </motion.div>
    );
  }

  // ── RESULTS ──────────────────────────────────────────────────────────────────
  if (quizComplete) {
    return (
      <motion.div
        key="results"
        initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: 'easeOut' }}
        className="w-full max-w-2xl mx-auto flex flex-col items-center text-center gap-8 py-16"
      >
        <p className="text-text-muted text-xs tracking-[0.2em] uppercase font-semibold">
          Your score
        </p>
        <p className="font-fraunces text-6xl md:text-7xl text-text-primary leading-none">
          {score}
          <span className="text-3xl text-text-muted font-light"> / {questions.length}</span>
        </p>
        <p className="text-text-muted font-light text-lg max-w-sm">
          {getReactionLine(score, questions.length)}
        </p>

        <div className="h-px w-24 bg-border-dark mt-2" />

        <div className="flex flex-col sm:flex-row items-center gap-4 mt-2">
          <motion.button
            onClick={onBackToComic}
            whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
            className="px-7 py-3 border border-border-dark bg-surface text-text-muted rounded-xl text-sm font-medium tracking-wide hover:border-text-muted hover:text-text-primary transition-all duration-300 cursor-pointer"
          >
            ← Back to comic
          </motion.button>
          <motion.button
            onClick={onReset}
            whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
            className="group relative flex items-center justify-center gap-2.5 px-7 py-3 border border-border-dark bg-surface text-text-muted rounded-xl text-sm font-medium tracking-wide overflow-hidden hover:border-accent/40 hover:shadow-[0_0_15px_rgba(232,163,61,0.15)] transition-all duration-300 cursor-pointer"
          >
            <div className="absolute inset-0 bg-gradient-to-r from-transparent via-accent/5 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-1000 ease-in-out" />
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4 text-accent group-hover:rotate-12 transition-transform duration-300">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
            </svg>
            <span className="relative z-10 group-hover:text-text-primary transition-colors duration-300">Explain another topic</span>
          </motion.button>
        </div>
      </motion.div>
    );
  }

  // ── QUIZ QUESTIONS ────────────────────────────────────────────────────────────
  const isLast = currentIndex === questions.length - 1;

  const getOptionStyle = (idx) => {
    if (!answered) {
      return 'border-border-dark text-text-primary hover:border-text-muted hover:bg-surface cursor-pointer';
    }
    if (idx === currentQ.correct_index) {
      return 'border-green-500/60 bg-green-500/10 text-green-400';
    }
    if (idx === selectedAnswer && idx !== currentQ.correct_index) {
      return 'border-red-400/60 bg-red-400/10 text-red-400';
    }
    return 'border-border-dark/40 text-text-muted/40 opacity-40';
  };

  return (
    <div className="w-full max-w-2xl mx-auto flex flex-col gap-10 py-4">

      {/* Back link */}
      <button
        onClick={onBackToComic}
        className="self-start text-xs text-text-muted hover:text-text-primary transition-colors cursor-pointer tracking-wide flex items-center gap-1.5"
      >
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="w-3.5 h-3.5">
          <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" />
        </svg>
        Back to comic
      </button>

      {/* Question card */}
      <AnimatePresence mode="wait" custom={direction}>
        <motion.div
          key={currentIndex}
          custom={direction}
          variants={slideVariants}
          initial="initial"
          animate="animate"
          exit="exit"
          className="flex flex-col gap-8"
        >
          {/* Progress */}
          <p className="text-accent text-xs tracking-[0.2em] uppercase font-semibold">
            Question {currentIndex + 1} of {questions.length}
          </p>

          {/* Question */}
          <p className="font-fraunces text-2xl md:text-3xl text-text-primary leading-[1.4] max-w-xl">
            {currentQ.question}
          </p>

          {/* Options */}
          <div className="flex flex-col gap-3">
            {currentQ.options.map((option, idx) => (
              <button
                key={idx}
                onClick={() => handleSelect(idx)}
                disabled={answered}
                className={`w-full flex items-center gap-4 text-left px-6 py-4 rounded-xl border bg-charcoal transition-all duration-200 text-sm font-inter ${getOptionStyle(idx)}`}
              >
                {/* Option letter */}
                <span className="shrink-0 w-6 h-6 rounded-full border border-current flex items-center justify-center text-xs font-semibold opacity-60">
                  {['A','B','C','D'][idx]}
                </span>
                <span className="flex-1">{option}</span>

                {/* Icon after answering */}
                {answered && idx === currentQ.correct_index && (
                  <svg className="w-4 h-4 shrink-0 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                  </svg>
                )}
                {answered && idx === selectedAnswer && idx !== currentQ.correct_index && (
                  <svg className="w-4 h-4 shrink-0 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                )}
              </button>
            ))}
          </div>

          {/* Explanation */}
          <AnimatePresence>
            {answered && (
              <motion.p
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.4 }}
                className="text-text-muted text-sm font-light leading-relaxed border-l-2 border-border-dark pl-4"
              >
                {currentQ.explanation}
              </motion.p>
            )}
          </AnimatePresence>
        </motion.div>
      </AnimatePresence>

      {/* Next / See Results button */}
      <AnimatePresence>
        {answered && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.35 }}
          >
            <motion.button
              onClick={handleNext}
              whileHover={{ scale: 1.02, filter: 'brightness(1.1)' }}
              whileTap={{ scale: 0.98 }}
              className="bg-accent text-charcoal font-medium text-sm px-8 py-3.5 rounded-xl cursor-pointer transition-colors"
            >
              {isLast ? 'See results' : 'Next question →'}
            </motion.button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

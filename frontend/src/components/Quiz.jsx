import { API_ENDPOINTS } from '../config/api';
import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import LanguageSwitcher from './LanguageSwitcher';
import { SUPPORTED_LANGUAGES } from '../config/languages';

const slideVariants = {
  initial: (dir) => ({ opacity: 0, x: dir > 0 ? 40 : -40 }),
  animate: { opacity: 1, x: 0, transition: { duration: 0.4, ease: 'easeOut' } },
  exit:    (dir) => ({ opacity: 0, x: dir > 0 ? -40 : 40, transition: { duration: 0.3, ease: 'easeIn' } }),
};

const QUIZ_UI_TEXT = {
  en: {
    backToComic: 'Back to comic',
    question: 'Question',
    of: 'of',
    yourScore: 'Your score',
    perfect: "Perfect — you've got this.",
    solid: 'Solid grasp, one gap to close.',
    review: 'Worth another pass through the comic.',
    nextQuestion: 'Next question →',
    seeResults: 'See results',
    explainAnother: 'Explain another topic',
    preparingQuiz: 'Preparing your quiz...',
    translatingQuiz: 'Translating quiz...',
    couldntGenerate: "Couldn't generate a quiz right now.",
    noQuestions: 'No quiz questions available for this topic.',
  },
  es: {
    backToComic: 'Volver al cómic',
    question: 'Pregunta',
    of: 'de',
    yourScore: 'Tu puntuación',
    perfect: '¡Perfecto! Dominas este tema.',
    solid: 'Buen entendimiento, casi perfecto.',
    review: 'Vale la pena repasar el cómic.',
    nextQuestion: 'Siguiente pregunta →',
    seeResults: 'Ver resultados',
    explainAnother: 'Explicar otro tema',
    preparingQuiz: 'Preparando tu cuestionario...',
    translatingQuiz: 'Traduciendo cuestionario...',
    couldntGenerate: 'No se pudo generar el cuestionario.',
    noQuestions: 'No hay preguntas disponibles para este tema.',
  },
  fr: {
    backToComic: 'Retour à la BD',
    question: 'Question',
    of: 'sur',
    yourScore: 'Votre score',
    perfect: 'Parfait — vous maîtrisez le sujet.',
    solid: 'Très bonne compréhension.',
    review: 'Une relecture de la BD serait utile.',
    nextQuestion: 'Question suivante →',
    seeResults: 'Voir les résultats',
    explainAnother: 'Expliquer un autre sujet',
    preparingQuiz: 'Préparation du quiz...',
    translatingQuiz: 'Traduction du quiz...',
    couldntGenerate: 'Impossible de générer le quiz.',
    noQuestions: 'Aucune question disponible pour ce sujet.',
  },
  de: {
    backToComic: 'Zurück zum Comic',
    question: 'Frage',
    of: 'von',
    yourScore: 'Dein Punktestand',
    perfect: 'Perfekt — du hast es voll verstanden.',
    solid: 'Solides Verständnis, fast perfekt.',
    review: 'Lies den Comic am besten noch einmal.',
    nextQuestion: 'Nächste Frage →',
    seeResults: 'Ergebnisse anzeigen',
    explainAnother: 'Anderes Thema erklären',
    preparingQuiz: 'Quiz wird vorbereitet...',
    translatingQuiz: 'Quiz wird übersetzt...',
    couldntGenerate: 'Quiz konnte nicht erstellt werden.',
    noQuestions: 'Keine Fragen verfügbar.',
  },
  hi: {
    backToComic: 'कॉमिक पर वापस जाएं',
    question: 'प्रश्न',
    of: 'का',
    yourScore: 'आपका स्कोर',
    perfect: 'बिल्कुल सही — आपने इसे समझ लिया!',
    solid: 'अच्छी पकड़, बस थोड़ा सा अभ्यास और।',
    review: 'कॉमिक को एक बार फिर देखना उपयोगी होगा।',
    nextQuestion: 'अगला प्रश्न →',
    seeResults: 'परिणाम देखें',
    explainAnother: 'दूसरे विषय को समझें',
    preparingQuiz: 'आपकी क्विज़ तैयार की जा रही है...',
    translatingQuiz: 'क्विज़ का अनुवाद किया जा रहा है...',
    couldntGenerate: 'क्विज़ तैयार नहीं हो सकी।',
    noQuestions: 'इस विषय के लिए प्रश्न उपलब्ध नहीं हैं।',
  },
  ur: {
    backToComic: 'کامک پر واپس جائیں',
    question: 'سوال',
    of: 'از',
    yourScore: 'آپ کا اسکور',
    perfect: 'بہترین — آپ نے یہ سیکھ لیا۔',
    solid: 'بہترین گرفت، تھوڑا سا مزید مطالعہ۔',
    review: 'کامک کو دوبارہ پڑھنا مفید ہوگا۔',
    nextQuestion: 'اگلا سوال ←',
    seeResults: 'نتائج دیکھیں',
    explainAnother: 'کوئی اور موضوع سمجھائیں',
    preparingQuiz: 'کوئز تیار کیا جا رہا ہے...',
    translatingQuiz: 'کوئز کا ترجمہ کیا جا رہا ہے...',
    couldntGenerate: 'کوئز تیار نہیں ہو سکا۔',
    noQuestions: 'اس موضوع کے لیے کوئی سوال دستیاب نہیں۔',
  },
  ar: {
    backToComic: 'العودة إلى القصة',
    question: 'السؤال',
    of: 'من',
    yourScore: 'درجتك',
    perfect: 'ممتاز — لقد استوعبت المفهوم تماماً.',
    solid: 'فهم قوي، خطوة بسيطة للإتقان.',
    review: 'من المفيد مراجعة القصة مرة أخرى.',
    nextQuestion: 'السؤال التالي ←',
    seeResults: 'عرض النتيجة',
    explainAnother: 'شرح موضوع آخر',
    preparingQuiz: 'جاري إعداد الاختبار...',
    translatingQuiz: 'جاري ترجمة الاختبار...',
    couldntGenerate: 'تعذر إنشاء الاختبار حالياً.',
    noQuestions: 'لا توجد أسئلة متاحة لهذا الموضوع.',
  },
  ja: {
    backToComic: 'マンガに戻る',
    question: '質問',
    of: '/',
    yourScore: 'あなたのスコア',
    perfect: '完璧です！完全に理解しました。',
    solid: '素晴らしい理解度です。',
    review: 'もう一度マンガを読んでみましょう。',
    nextQuestion: '次の質問 →',
    seeResults: '結果を見る',
    explainAnother: '別のトピックを解説する',
    preparingQuiz: 'クイズを準備中...',
    translatingQuiz: 'クイズを翻訳中...',
    couldntGenerate: 'クイズを生成できませんでした。',
    noQuestions: '利用可能なクイズがありません。',
  },
  zh: {
    backToComic: '返回漫画',
    question: '题目',
    of: '/',
    yourScore: '你的得分',
    perfect: '太棒了——你已经完全掌握了。',
    solid: '理解扎实，只差一点就完美了。',
    review: '建议再次阅读漫画加深理解。',
    nextQuestion: '下一题 →',
    seeResults: '查看结果',
    explainAnother: '解释另一个主题',
    preparingQuiz: '正在准备测验...',
    translatingQuiz: '正在翻译测验...',
    couldntGenerate: '暂时无法生成测验。',
    noQuestions: '暂无可用测验题目。',
  },
  pt: {
    backToComic: 'Voltar aos quadrinhos',
    question: 'Pergunta',
    of: 'de',
    yourScore: 'Sua pontuação',
    perfect: 'Perfeito — você dominou este conceito.',
    solid: 'Ótima compreensão, quase lá.',
    review: 'Vale a pena reler os quadrinhos.',
    nextQuestion: 'Próxima pergunta →',
    seeResults: 'Ver resultados',
    explainAnother: 'Explicar outro tópico',
    preparingQuiz: 'Preparando seu quiz...',
    translatingQuiz: 'Traduzindo o quiz...',
    couldntGenerate: 'Não foi possível gerar o quiz agora.',
    noQuestions: 'Nenhuma pergunta disponível para este tema.',
  },
};

function getReactionLine(score, total, langCode) {
  const dict = QUIZ_UI_TEXT[langCode] || QUIZ_UI_TEXT.en;
  const ratio = score / total;
  if (ratio === 1)   return dict.perfect;
  if (ratio >= 0.66) return dict.solid;
  return dict.review;
}

export default function Quiz({
  topic,
  activeLang = SUPPORTED_LANGUAGES[0],
  onSelectLanguage,
  isTranslating = false,
  onBackToComic,
  onReset
}) {
  const [status, setStatus]               = useState('loading');   // 'loading' | 'ready' | 'error'
  const [questions, setQuestions]         = useState([]);
  const [currentIndex, setCurrentIndex]   = useState(0);
  const [direction, setDirection]         = useState(1);
  const [selectedAnswer, setSelectedAnswer] = useState(null);
  const [answered, setAnswered]           = useState(false);
  const [score, setScore]                 = useState(0);
  const [quizComplete, setQuizComplete]   = useState(false);
  const [localTranslating, setLocalTranslating] = useState(false);

  const quizCacheRef = useRef({});
  const initialFetchDoneRef = useRef(false);

  const t = QUIZ_UI_TEXT[activeLang?.code] || QUIZ_UI_TEXT.en;

  // 1. Initial quiz fetch
  useEffect(() => {
    let isCancelled = false;

    const fetchInitialQuiz = async () => {
      setStatus('loading');
      try {
        const res = await fetch(API_ENDPOINTS.GENERATE_QUIZ, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            topic,
            target_language: activeLang?.name || 'English',
            target_code: activeLang?.code || 'en'
          }),
        });
        if (!res.ok) throw new Error('Bad response');
        const data = await res.json();
        if (!data.questions || !Array.isArray(data.questions) || data.questions.length === 0) {
          throw new Error('No questions generated');
        }

        if (!isCancelled) {
          quizCacheRef.current[activeLang?.code || 'en'] = data.questions;
          setQuestions(data.questions);
          setStatus('ready');
          initialFetchDoneRef.current = true;
        }
      } catch {
        if (!isCancelled) {
          setStatus('error');
        }
      }
    };

    fetchInitialQuiz();

    return () => {
      isCancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topic]);

  // 2. React to language changes after initial quiz is loaded
  useEffect(() => {
    if (!initialFetchDoneRef.current || questions.length === 0) return;

    const currentLangCode = activeLang?.code || 'en';

    // A. Check in-memory cache for instant 0ms switch
    if (quizCacheRef.current[currentLangCode]) {
      setQuestions(quizCacheRef.current[currentLangCode]);
      return;
    }

    // B. Call lightning-fast /translate-quiz
    let isCancelled = false;
    const translateExistingQuiz = async () => {
      setLocalTranslating(true);
      try {
        // Base questions to translate (prefer English if cached, otherwise current questions)
        const baseQuestions = quizCacheRef.current['en'] || questions;
        const res = await fetch(API_ENDPOINTS.TRANSLATE_QUIZ, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            questions: baseQuestions,
            target_language: activeLang?.name || 'English',
            target_code: currentLangCode,
          }),
        });

        if (!res.ok) throw new Error('Translation failed');
        const data = await res.json();
        if (data.translated_questions && Array.isArray(data.translated_questions)) {
          if (!isCancelled) {
            quizCacheRef.current[currentLangCode] = data.translated_questions;
            setQuestions(data.translated_questions);
          }
        }
      } catch (err) {
        console.error('Failed to translate quiz:', err);
      } finally {
        if (!isCancelled) {
          setLocalTranslating(false);
        }
      }
    };

    translateExistingQuiz();

    return () => {
      isCancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeLang?.code]);

  const currentQ = questions[currentIndex];

  const handleSelect = (idx) => {
    if (answered || !currentQ) return;
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
          {t.preparingQuiz}
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
          {t.couldntGenerate}
        </p>
        <button
          onClick={onBackToComic}
          className="text-sm text-text-muted hover:text-text-primary underline transition-colors cursor-pointer"
        >
          ← {t.backToComic}
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
        {/* Language selector in results */}
        {onSelectLanguage && (
          <div className="self-end mb-2">
            <LanguageSwitcher
              activeLang={activeLang}
              onSelectLanguage={onSelectLanguage}
              isTranslating={isTranslating || localTranslating}
            />
          </div>
        )}

        <p className="text-text-muted text-xs tracking-[0.2em] uppercase font-semibold">
          {t.yourScore}
        </p>
        <p className="font-fraunces text-6xl md:text-7xl text-text-primary leading-none">
          {score}
          <span className="text-3xl text-text-muted font-light"> / {questions.length}</span>
        </p>
        <p className="text-text-muted font-light text-lg max-w-sm">
          {getReactionLine(score, questions.length, activeLang?.code)}
        </p>

        <div className="h-px w-24 bg-border-dark mt-2" />

        <div className="flex flex-col sm:flex-row items-center gap-4 mt-2">
          <motion.button
            onClick={onBackToComic}
            whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
            className="px-7 py-3 border border-border-dark bg-surface text-text-muted rounded-xl text-sm font-medium tracking-wide hover:border-text-muted hover:text-text-primary transition-all duration-300 cursor-pointer"
          >
            ← {t.backToComic}
          </motion.button>
          <motion.button
            onClick={() => {
              if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
                window.speechSynthesis.cancel();
              }
              onReset();
            }}
            whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
            className="group relative flex items-center justify-center gap-2.5 px-7 py-3 border border-border-dark bg-surface text-text-muted rounded-xl text-sm font-medium tracking-wide overflow-hidden hover:border-accent/40 hover:shadow-[0_0_15px_rgba(232,163,61,0.15)] transition-all duration-300 cursor-pointer"
          >
            <div className="absolute inset-0 bg-gradient-to-r from-transparent via-accent/5 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-1000 ease-in-out" />
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4 text-accent group-hover:rotate-12 transition-transform duration-300">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
            </svg>
            <span className="relative z-10 group-hover:text-text-primary transition-colors duration-300">{t.explainAnother}</span>
          </motion.button>
        </div>
      </motion.div>
    );
  }

  // ── EMPTY / GUARD CHECK ─────────────────────────────────────────────────────
  if (!currentQ || questions.length === 0) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-2xl mx-auto flex flex-col items-center gap-6 py-24"
      >
        <p className="text-text-muted font-light text-lg">
          {t.noQuestions}
        </p>
        <div className="flex gap-4">
          <button
            onClick={onBackToComic}
            className="text-sm text-text-muted hover:text-text-primary underline transition-colors cursor-pointer"
          >
            ← {t.backToComic}
          </button>
          <button
            onClick={() => {
              if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
                window.speechSynthesis.cancel();
              }
              onReset();
            }}
            className="text-sm text-accent hover:underline transition-colors cursor-pointer"
          >
            {t.explainAnother}
          </button>
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

      {/* Top Bar inside Quiz: Back link + Language Switcher */}
      <div className="flex items-center justify-between w-full flex-wrap gap-3">
        <button
          onClick={onBackToComic}
          className="text-xs text-text-muted hover:text-text-primary transition-colors cursor-pointer tracking-wide flex items-center gap-1.5"
        >
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="w-3.5 h-3.5">
            <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" />
          </svg>
          {t.backToComic}
        </button>

        {onSelectLanguage && (
          <LanguageSwitcher
            activeLang={activeLang}
            onSelectLanguage={onSelectLanguage}
            isTranslating={isTranslating || localTranslating}
          />
        )}
      </div>

      {/* Translating banner indicator */}
      {localTranslating && (
        <motion.div
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center justify-center gap-2 py-2 px-4 rounded-xl bg-accent/10 border border-accent/30 text-accent text-xs font-medium"
        >
          <div className="w-3 h-3 rounded-full border-2 border-accent border-t-transparent animate-spin" />
          <span>{t.translatingQuiz}</span>
        </motion.div>
      )}

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
          {/* Progress Badge */}
          <div className="flex items-center justify-between">
            <p className="text-accent text-xs tracking-[0.2em] uppercase font-semibold">
              {t.question} {currentIndex + 1} {t.of} {questions.length}
            </p>
          </div>

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
                disabled={answered || localTranslating}
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
              disabled={localTranslating}
              whileHover={{ scale: 1.02, filter: 'brightness(1.1)' }}
              whileTap={{ scale: 0.98 }}
              className="bg-accent text-charcoal font-medium text-sm px-8 py-3.5 rounded-xl cursor-pointer transition-colors"
            >
              {isLast ? t.seeResults : t.nextQuestion}
            </motion.button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

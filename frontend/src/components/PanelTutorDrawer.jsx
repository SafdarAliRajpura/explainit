import { useLanguage } from '../hooks/useLanguage';
import { API_ENDPOINTS } from '../config/api';
import { useState, useEffect, useRef, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

// Lightweight, safe formatting helper for markdown-like AI responses
function FormattedMessage({ text }) {
  if (!text) return null;

  // Split into paragraphs / blocks
  const blocks = text.split(/\n\s*\n/);

  return (
    <div className="space-y-3 text-sm leading-relaxed text-text-primary">
      {blocks.map((block, bIdx) => {
        const trimmed = block.trim();
        if (!trimmed) return null;

        // Headings: ### Header or ## Header
        if (trimmed.startsWith('### ') || trimmed.startsWith('## ')) {
          const headingText = trimmed.replace(/^#{2,3}\s+/, '');
          return (
            <h4 key={bIdx} className="font-semibold text-accent text-sm tracking-wide pt-1">
              {headingText}
            </h4>
          );
        }

        // Bullet lists (* or -)
        if (trimmed.startsWith('* ') || trimmed.startsWith('- ')) {
          const items = trimmed.split(/\n\s*[*|-]\s+/).filter(Boolean);
          return (
            <ul key={bIdx} className="space-y-1.5 pl-2">
              {items.map((item, iIdx) => (
                <li key={iIdx} className="flex items-start gap-2 text-text-primary/90">
                  <span className="text-accent text-xs mt-1 shrink-0">●</span>
                  <span>{renderInlineFormatting(item)}</span>
                </li>
              ))}
            </ul>
          );
        }

        // Numbered lists (1. , 2. )
        if (/^\d+\.\s+/.test(trimmed)) {
          const items = trimmed.split(/\n\s*\d+\.\s+/).filter(Boolean);
          return (
            <ol key={bIdx} className="space-y-1.5 pl-2">
              {items.map((item, iIdx) => (
                <li key={iIdx} className="flex items-start gap-2 text-text-primary/90">
                  <span className="text-accent font-mono text-xs mt-0.5 shrink-0">{iIdx + 1}.</span>
                  <span>{renderInlineFormatting(item)}</span>
                </li>
              ))}
            </ol>
          );
        }

        // Callout box (> or 💡 or 🔍)
        if (trimmed.startsWith('>') || trimmed.startsWith('💡') || trimmed.startsWith('🔍') || trimmed.startsWith('⚠️')) {
          const calloutText = trimmed.replace(/^>\s*/, '');
          return (
            <div key={bIdx} className="p-3 rounded-xl bg-accent/10 border border-accent/25 text-text-primary text-xs leading-relaxed my-2">
              {renderInlineFormatting(calloutText)}
            </div>
          );
        }

        // Standard paragraph
        return (
          <p key={bIdx} className="text-text-primary/90">
            {renderInlineFormatting(trimmed)}
          </p>
        );
      })}
    </div>
  );
}

// Inline formatting: **bold**, `code`
function renderInlineFormatting(rawText) {
  if (!rawText) return '';

  // Tokenize by code snippets `code` and bold **text**
  const parts = rawText.split(/(`[^`]+`|\*\*[^*]+\*\*)/g);

  return parts.map((part, idx) => {
    if (part.startsWith('`') && part.endsWith('`')) {
      return (
        <code key={idx} className="px-1.5 py-0.5 rounded bg-[#1C1F26] text-accent font-mono text-xs border border-[#2D3139]">
          {part.slice(1, -1)}
        </code>
      );
    }
    if (part.startsWith('**') && part.endsWith('**')) {
      return (
        <strong key={idx} className="font-semibold text-text-primary">
          {part.slice(2, -2)}
        </strong>
      );
    }
    return part;
  });
}

const DEFAULT_SUGGESTIONS = [
  { label: 'Explain simpler', icon: '💡', prompt: 'Can you explain this step like I am 5 with a simple everyday metaphor?' },
  { label: 'Real-world example', icon: '🌍', prompt: 'What is a concrete real-world or industry example of this step in action?' },
  { label: 'Common misconceptions', icon: '⚠️', prompt: 'What do people usually get wrong or misunderstand about this step?' },
  { label: 'Technical depth / math', icon: '⚙️', prompt: 'Can you dive deeper into the technical mechanics and tradeoffs of this step?' },
];

export default function PanelTutorDrawer({
  isOpen,
  onClose,
  topic,
  currentPanel,
  totalPanels = 3,
  sourceCitation,
}) {
  const { activeLang, t } = useLanguage();
  const panelNum = currentPanel?.panel_number || 1;
  const panelCaption = currentPanel?.caption || '';
  const panelImage = currentPanel?.image_url;

  // Key messages by panel number so conversation persists when browsing between panels
  const [panelChatHistory, setPanelChatHistory] = useState({});
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  // Active messages for current panel (memoized with default initial greeting)
  const messages = useMemo(() => {
    const history = panelChatHistory[panelNum];
    if (history && history.length > 0) {
      return history;
    }
    return [{
      id: `welcome-${panelNum}`,
      role: 'assistant',
      content: `👋 **Welcome! I'm your AI tutor for Step ${panelNum}.**\n\nI'm specifically focused on what's happening right here: *"${panelCaption}"*.\n\nAsk me why this stage is necessary, how it works under the hood, or tap one of the suggested questions below to start!`,
      suggested_followups: [
        'Why does this step have to happen here?',
        'What is a real-world example of this?',
        'Explain this with a simple analogy'
      ],
      timestamp: null,
    }];
  }, [panelChatHistory, panelNum, panelCaption]);



  // Auto-scroll on new message
  useEffect(() => {
    if (isOpen) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages.length, isLoading, isOpen]);

  // Focus input when opened
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => {
        inputRef.current?.focus();
      }, 300);
    }
  }, [isOpen]);

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  const handleSend = async (questionText) => {
    const query = (questionText || input).trim();
    if (!query || isLoading) return;

    setInput('');

    const userMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: query,
      timestamp: null,
    };

    // Update state with user message immediately
    const updatedMessages = [...messages, userMessage];
    setPanelChatHistory(prev => ({
      ...prev,
      [panelNum]: updatedMessages,
    }));

    setIsLoading(true);

    try {
      // Build conversation history for context
      const historyPayload = updatedMessages.slice(-6).map(m => ({
        role: m.role,
        content: m.content
      }));

      const res = await fetch(API_ENDPOINTS.ASK_PANEL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          topic,
          panel_number: panelNum,
          panel_caption: panelCaption,
          question: query,
          conversation_history: historyPayload,
          target_language: activeLang?.name || 'English',
          target_code: activeLang?.code || 'en',
        }),
      });

      if (!res.ok) {
        throw new Error(`Server returned ${res.status}`);
      }

      const data = await res.json();

      const tutorMessage = {
        id: `tutor-${Date.now()}`,
        role: 'assistant',
        content: data.answer || "I've analyzed this step, but couldn't formulate a response. What else would you like to know?",
        suggested_followups: data.suggested_followups || [],
        timestamp: null,
      };

      setPanelChatHistory(prev => ({
        ...prev,
        [panelNum]: [...updatedMessages, tutorMessage],
      }));
    } catch (err) {
      console.error('AskPanel error:', err);
      const errorMessage = {
        id: `error-${Date.now()}`,
        role: 'assistant',
        content: `⚠️ **Couldn't reach the AI Tutor:** ${err.message || 'Please check your connection.'}\n\nHere is a quick summary for Step ${panelNum}: **${panelCaption}** establishes the core state before progressing.`,
        suggested_followups: ['Try asking again', 'Give me a simple example'],
        timestamp: null,
      };
      setPanelChatHistory(prev => ({
        ...prev,
        [panelNum]: [...updatedMessages, errorMessage],
      }));
    } finally {
      setIsLoading(false);
    }
  };

  const handleClearHistory = () => {
    setPanelChatHistory(prev => ({
      ...prev,
      [panelNum]: [{
        id: `welcome-${panelNum}-${Date.now()}`,
        role: 'assistant',
        content: `👋 **Chat reset for Step ${panelNum}.** Ask me anything about *"${panelCaption}"*!`,
        suggested_followups: [
          'Explain simpler',
          'Real-world example',
          'Common misconceptions'
        ],
        timestamp: null,
      }]
    }));
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-50 flex justify-end">
          {/* Backdrop Overlay */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
            onClick={onClose}
            className="fixed inset-0 bg-black/70 backdrop-blur-sm cursor-pointer"
          />

          {/* Slide-out Drawer Panel */}
          <motion.div
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 28, stiffness: 260 }}
            className="relative z-10 w-full sm:w-[480px] md:w-[540px] max-w-full h-full bg-[#0E1013] border-l border-[#262930] shadow-2xl flex flex-col justify-between overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {/* ── Top Header ────────────────────────────────────────── */}
            <div className="p-4 sm:p-5 border-b border-[#20232A] bg-[#12151A]/80 backdrop-blur-md flex items-center justify-between shrink-0">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-accent/15 border border-accent/30 flex items-center justify-center text-accent shadow-sm">
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
                    <path fillRule="evenodd" d="M4.804 21.644A6.707 6.707 0 006 21.75a6.721 6.721 0 003.583-1.029c.774.182 1.584.279 2.417.279 5.322 0 9.75-3.97 9.75-9 0-5.03-4.428-9-9.75-9s-9.75 3.97-9.75 9c0 2.409 1.025 4.587 2.674 6.192.232.226.277.428.254.543a3.73 3.73 0 01-.814 1.686.75.75 0 00.44 1.223zM8.25 10.875a1.125 1.125 0 100 2.25 1.125 1.125 0 000-2.25zm4.875-1.125a1.125 1.125 0 100 2.25 1.125 1.125 0 000-2.25zm3.75 1.125a1.125 1.125 0 100 2.25 1.125 1.125 0 000-2.25z" clipRule="evenodd" />
                  </svg>
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold text-text-primary text-base">{t('interactiveStepTutor')}</h3>
                    <span className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-full bg-accent/20 text-accent font-bold border border-accent/40">
                      {t('panelOf', { current: panelNum, total: totalPanels })}
                    </span>
                  </div>
                  <p className="text-xs text-text-muted truncate max-w-[260px] sm:max-w-[320px]">
                    {topic}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-1.5">
                {/* Reset Chat for this panel */}
                <button
                  onClick={handleClearHistory}
                  title="Clear chat history for this step"
                  className="p-2 rounded-lg text-text-muted hover:text-text-primary hover:bg-[#1A1D24] transition-colors cursor-pointer"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
                  </svg>
                </button>

                {/* Close Drawer Button */}
                <button
                  onClick={onClose}
                  className="p-2 rounded-lg text-text-muted hover:text-text-primary hover:bg-[#1A1D24] transition-colors cursor-pointer"
                  title={t('close')}
                >
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="w-5 h-5">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>

            {/* ── Pinned Panel Reference Preview ─────────────────────── */}
            <div className="px-4 sm:px-5 py-2.5 bg-[#14171E] border-b border-[#20232A] flex items-center justify-between text-xs">
              <div className="flex items-center gap-3 overflow-hidden">
                {panelImage && (
                  <div className="w-10 h-10 rounded-lg overflow-hidden border border-[#2A2E38] shrink-0 bg-surface">
                    <img src={panelImage} alt={`Step ${panelNum}`} className="w-full h-full object-cover" />
                  </div>
                )}
                <div className="overflow-hidden">
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] font-semibold text-accent uppercase tracking-wider">
                      Grounded on Step {panelNum}:
                    </span>
                    {sourceCitation?.url && (
                      <a
                        href={sourceCitation.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-[10px] text-text-muted hover:text-accent underline flex items-center gap-1 transition-colors"
                        title={sourceCitation.title || 'Source Citation'}
                      >
                        <span>[Source ↗]</span>
                      </a>
                    )}
                  </div>
                  <div className="text-text-primary/90 font-fraunces text-xs truncate max-w-[320px] sm:max-w-[380px]">
                    "{panelCaption}"
                  </div>
                </div>
              </div>
            </div>

            {/* ── Chat Messages Container ───────────────────────────── */}
            <div className="flex-1 overflow-y-auto p-4 sm:p-5 space-y-4">
              {messages.map((msg) => {
                const isAssistant = msg.role === 'assistant';

                return (
                  <motion.div
                    key={msg.id}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.25 }}
                    className={`flex flex-col ${isAssistant ? 'items-start' : 'items-end'}`}
                  >
                    {/* Message Bubble */}
                    <div
                      className={`max-w-[90%] sm:max-w-[85%] rounded-2xl p-4 shadow-sm ${
                        isAssistant
                          ? 'bg-[#15181F] border border-[#242832] text-text-primary'
                          : 'bg-accent/15 border border-accent/40 text-text-primary'
                      }`}
                    >
                      {/* Avatar & Label Header */}
                      <div className="flex items-center gap-2 mb-2">
                        {isAssistant ? (
                          <>
                            <span className="w-5 h-5 rounded-full bg-accent/20 text-accent flex items-center justify-center text-[10px] font-bold">
                              ✨
                            </span>
                            <span className="text-[11px] font-semibold text-accent tracking-wide">
                              AI Tutor
                            </span>
                          </>
                        ) : (
                          <span className="text-[11px] font-semibold text-accent ml-auto">
                            You
                          </span>
                        )}
                      </div>

                      {/* Content */}
                      <FormattedMessage text={msg.content} />
                    </div>

                    {/* Dynamic Follow-Up Suggestions (if provided by assistant) */}
                    {isAssistant && msg.suggested_followups && msg.suggested_followups.length > 0 && (
                      <div className="mt-2.5 flex flex-wrap gap-1.5 max-w-[90%] pl-2">
                        {msg.suggested_followups.map((followup, fIdx) => (
                          <button
                            key={fIdx}
                            onClick={() => handleSend(followup)}
                            disabled={isLoading}
                            className="text-left text-xs px-2.5 py-1 rounded-full bg-[#181B22] hover:bg-accent/15 border border-[#2A2E38] hover:border-accent/40 text-text-muted hover:text-accent transition-all cursor-pointer shadow-sm flex items-center gap-1.5 group"
                          >
                            <span className="text-[10px] text-accent group-hover:scale-110 transition-transform">💬</span>
                            <span>{followup}</span>
                          </button>
                        ))}
                      </div>
                    )}
                  </motion.div>
                );
              })}

              {/* Typing / Thinking Indicator */}
              {isLoading && (
                <motion.div
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="flex items-center gap-2 p-3.5 rounded-2xl bg-[#15181F] border border-[#242832] w-fit shadow-sm"
                >
                  <span className="w-5 h-5 rounded-full bg-accent/20 text-accent flex items-center justify-center text-[10px] font-bold">
                    ✨
                  </span>
                  <div className="flex items-center gap-1.5 px-2">
                    <span className="w-1.5 h-1.5 rounded-full bg-accent animate-bounce" style={{ animationDelay: '0ms' }} />
                    <span className="w-1.5 h-1.5 rounded-full bg-accent animate-bounce" style={{ animationDelay: '150ms' }} />
                    <span className="w-1.5 h-1.5 rounded-full bg-accent animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                  <span className="text-xs text-text-muted font-medium">Tutor is synthesizing...</span>
                </motion.div>
              )}

              <div ref={messagesEndRef} />
            </div>

            {/* ── Suggested Prompts Chips Bar ──────────────────────── */}
            <div className="p-3 border-t border-[#20232A] bg-[#101217]/95">
              <div className="text-[10px] uppercase font-semibold text-text-muted tracking-wider mb-2 px-1">
                {t('suggestedInquiries')}:
              </div>
              <div className="flex gap-1.5 overflow-x-auto pb-1 scrollbar-none">
                {DEFAULT_SUGGESTIONS.map((sug, sIdx) => (
                  <button
                    key={sIdx}
                    onClick={() => handleSend(sug.prompt)}
                    disabled={isLoading}
                    className="shrink-0 text-xs px-3 py-1.5 rounded-xl bg-[#181B24] hover:bg-accent/15 border border-[#2B303C] hover:border-accent/40 text-text-primary hover:text-accent font-medium transition-all cursor-pointer shadow-sm flex items-center gap-1.5 group disabled:opacity-50"
                  >
                    <span>{sug.icon}</span>
                    <span>{sug.label}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* ── Bottom Input Bar ──────────────────────────────────── */}
            <div className="p-3 sm:p-4 border-t border-[#20232A] bg-[#12151B]">
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  handleSend();
                }}
                className="flex items-center gap-2"
              >
                <div className="relative flex-1">
                  <input
                    ref={inputRef}
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder={t('typeQuestionPlaceholder')}
                    disabled={isLoading}
                    className="w-full pl-3.5 pr-4 py-3 rounded-xl bg-[#191D24] border border-[#2A2F3B] focus:border-accent/60 text-text-primary placeholder:text-text-muted/60 text-sm focus:outline-none transition-colors shadow-inner"
                  />
                </div>

                <button
                  type="submit"
                  disabled={!input.trim() || isLoading}
                  className="h-11 px-4 rounded-xl bg-accent hover:bg-accent/90 disabled:opacity-40 disabled:cursor-not-allowed text-charcoal font-semibold text-xs sm:text-sm flex items-center justify-center gap-1.5 cursor-pointer transition-all shadow-sm shrink-0"
                  title="Send question"
                >
                  <span>{t('send')}</span>
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
                    <path d="M3.105 2.289a.75.75 0 00-.826.95l1.414 4.925A1.5 1.5 0 005.135 9.25h6.115a.75.75 0 010 1.5H5.135a1.5 1.5 0 00-1.442 1.086l-1.414 4.926a.75.75 0 00.826.95 28.896 28.896 0 0015.293-7.154.75.75 0 000-1.115A28.897 28.897 0 003.105 2.289z" />
                  </svg>
                </button>
              </form>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}

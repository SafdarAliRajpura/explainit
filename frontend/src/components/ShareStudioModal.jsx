import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { jsPDF } from 'jspdf';

export default function ShareStudioModal({
  isOpen,
  onClose,
  topic,
  panels,
  linkedinConnected,
  linkedinName,
  onConnectLinkedin,
  onDirectPost,
}) {
  const [currentSlide, setCurrentSlide] = useState(0);
  const [isGeneratingPdf, setIsGeneratingPdf] = useState(false);
  const [isGeneratingPoster, setIsGeneratingPoster] = useState(false);
  const [pdfSuccess, setPdfSuccess] = useState(false);
  const [posterSuccess, setPosterSuccess] = useState(false);
  
  // LinkedIn copy generator state
  const [postCopy, setPostCopy] = useState(null);
  const [loadingCopy, setLoadingCopy] = useState(false);
  const [copySuccess, setCopySuccess] = useState(false);

  // Direct post state
  const [directPosting, setDirectPosting] = useState(false);
  const [directPostSuccess, setDirectPostSuccess] = useState(false);

  const totalSlides = (panels?.length || 3) + 2; // Cover + Panels (3) + Summary Slide = 5

  // 1. Fetch AI-generated LinkedIn copy when modal opens
  useEffect(() => {
    if (!isOpen || !topic) return;

    const fetchLinkedInCopy = async () => {
      setLoadingCopy(true);
      try {
        const res = await fetch('http://localhost:8000/generate-linkedin-copy', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ topic, panels })
        });
        if (res.ok) {
          const data = await res.json();
          setPostCopy(data);
        } else {
          throw new Error('Fallback');
        }
      } catch (err) {
        // Fallback copy
        setPostCopy({
          hook: `Ever wondered how ${topic} really works? Here is the 3-step visual breakdown: 👇`,
          takeaways: panels.map((p, i) => `Step ${i + 1}: ${p.caption}`),
          cta: `Swipe through the carousel above 👆 for the full visual story! Save this post 📌 so you don't lose it.`,
          hashtags: ['#ExplainIT', '#VisualLearning', '#TechExplainer', '#Education']
        });
      } finally {
        setLoadingCopy(false);
      }
    };

    fetchLinkedInCopy();
  }, [isOpen, topic, panels]);

  // Helper to load image as HTML Image element
  const loadImage = (url) => {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.crossOrigin = 'anonymous';
      img.onload = () => resolve(img);
      img.onerror = (e) => reject(e);
      img.src = url;
    });
  };

  // Helper: word wrap text on canvas
  const wrapText = (ctx, text, x, y, maxWidth, lineHeight) => {
    const words = text.split(' ');
    let line = '';
    let currentY = y;

    for (let n = 0; n < words.length; n++) {
      const testLine = line + words[n] + ' ';
      const metrics = ctx.measureText(testLine);
      const testWidth = metrics.width;
      if (testWidth > maxWidth && n > 0) {
        ctx.fillText(line, x, currentY);
        line = words[n] + ' ';
        currentY += lineHeight;
      } else {
        line = testLine;
      }
    }
    ctx.fillText(line, x, currentY);
    return currentY + lineHeight;
  };

  // 2. Render a 1080x1350 canvas for a specific slide
  const renderSlideCanvas = async (slideIdx) => {
    const canvas = document.createElement('canvas');
    canvas.width = 1080;
    canvas.height = 1350;
    const ctx = canvas.getContext('2d');

    // Gradient Background
    const grad = ctx.createLinearGradient(0, 0, 1080, 1350);
    grad.addColorStop(0, '#0F1117');
    grad.addColorStop(0.5, '#15171A');
    grad.addColorStop(1, '#0B0C0E');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, 1080, 1350);

    // Subtle Grid lines
    ctx.strokeStyle = '#1E222B';
    ctx.lineWidth = 1;
    for (let x = 100; x < 1080; x += 200) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, 1350);
      ctx.stroke();
    }

    // Outer Border
    ctx.strokeStyle = '#262930';
    ctx.lineWidth = 4;
    ctx.strokeRect(36, 36, 1008, 1278);

    // Universal Header
    ctx.fillStyle = '#E8A33D';
    ctx.font = 'bold 22px system-ui, sans-serif';
    ctx.fillText('EXPLAINIT', 70, 90);
    ctx.fillStyle = '#8B8D93';
    ctx.font = '16px system-ui, sans-serif';
    ctx.fillText('• VERIFIED VISUAL EXPLAINER', 195, 90);

    // Slide Counter Top Right
    ctx.fillStyle = '#8B8D93';
    ctx.font = 'bold 18px system-ui, sans-serif';
    ctx.textAlign = 'right';
    ctx.fillText(`${slideIdx + 1} / ${totalSlides}`, 1010, 90);
    ctx.textAlign = 'left';

    // SLIDE 0: COVER SLIDE
    if (slideIdx === 0) {
      // Amber Badge
      ctx.fillStyle = 'rgba(232, 163, 61, 0.15)';
      ctx.fillRect(70, 240, 280, 48);
      ctx.strokeStyle = '#E8A33D';
      ctx.lineWidth = 2;
      ctx.strokeRect(70, 240, 280, 48);
      ctx.fillStyle = '#E8A33D';
      ctx.font = 'bold 16px system-ui, sans-serif';
      ctx.fillText('ILLUSTRATED 3-STEP GUIDE', 95, 271);

      // Topic Title
      ctx.fillStyle = '#F2F1ED';
      ctx.font = 'bold 64px system-ui, serif';
      wrapText(ctx, topic, 70, 380, 940, 78);

      // Subtitle
      ctx.fillStyle = '#94A3B8';
      ctx.font = '24px system-ui, sans-serif';
      ctx.fillText('A visual, fact-checked breakdown of the core mechanism.', 70, 600);

      // Hero Center Graphic / Decorative Element
      ctx.strokeStyle = '#262930';
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.arc(540, 840, 160, 0, Math.PI * 2);
      ctx.stroke();

      ctx.strokeStyle = '#E8A33D';
      ctx.lineWidth = 4;
      ctx.beginPath();
      ctx.arc(540, 840, 120, 0, Math.PI * 2);
      ctx.stroke();

      ctx.fillStyle = '#E8A33D';
      ctx.beginPath();
      ctx.arc(540, 840, 24, 0, Math.PI * 2);
      ctx.fill();

      // Swipe Indicator Bottom
      ctx.fillStyle = '#E8A33D';
      ctx.font = 'bold 22px system-ui, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('Swipe to explore the breakdown →', 540, 1220);
      ctx.textAlign = 'left';

    } else if (slideIdx >= 1 && slideIdx <= (panels?.length || 3)) {
      // PANEL SLIDES (1, 2, 3)
      const panel = panels[slideIdx - 1];

      // Step Tag
      ctx.fillStyle = 'rgba(232, 163, 61, 0.15)';
      ctx.fillRect(70, 140, 150, 40);
      ctx.strokeStyle = '#E8A33D';
      ctx.lineWidth = 2;
      ctx.strokeRect(70, 140, 150, 40);
      ctx.fillStyle = '#E8A33D';
      ctx.font = 'bold 16px system-ui, sans-serif';
      ctx.fillText(`STEP ${slideIdx} OF 3`, 95, 166);

      // Draw SVG Panel Image into 880x880 Box
      if (panel?.image_url) {
        try {
          const img = await loadImage(panel.image_url);
          ctx.drawImage(img, 100, 210, 880, 880);
          ctx.strokeStyle = '#262930';
          ctx.lineWidth = 2;
          ctx.strokeRect(100, 210, 880, 880);
        } catch (e) {
          ctx.fillStyle = '#161B26';
          ctx.fillRect(100, 210, 880, 880);
        }
      }

      // Caption Box at Bottom
      ctx.fillStyle = '#F2F1ED';
      ctx.font = '24px system-ui, serif';
      wrapText(ctx, panel?.caption || '', 100, 1140, 880, 36);

      // Swipe prompt
      ctx.fillStyle = '#8B8D93';
      ctx.font = '16px system-ui, sans-serif';
      ctx.textAlign = 'right';
      ctx.fillText('Swipe →', 980, 1260);
      ctx.textAlign = 'left';

    } else {
      // SLIDE 4 / 5: SUMMARY & KEY TAKEAWAYS
      ctx.fillStyle = 'rgba(16, 185, 129, 0.15)';
      ctx.fillRect(70, 160, 240, 44);
      ctx.strokeStyle = '#10B981';
      ctx.lineWidth = 2;
      ctx.strokeRect(70, 160, 240, 44);
      ctx.fillStyle = '#10B981';
      ctx.font = 'bold 16px system-ui, sans-serif';
      ctx.fillText('KEY TAKEAWAYS', 95, 188);

      ctx.fillStyle = '#F2F1ED';
      ctx.font = 'bold 44px system-ui, serif';
      ctx.fillText('Summary & Core Learnings', 70, 260);

      // 3 Summary Cards
      const takeaways = postCopy?.takeaways || panels.map((p, i) => `Step ${i + 1}: ${p.caption}`);
      let cardY = 320;
      takeaways.slice(0, 3).forEach((item, idx) => {
        ctx.fillStyle = '#161B26';
        ctx.fillRect(70, cardY, 940, 160);
        ctx.strokeStyle = '#262930';
        ctx.lineWidth = 2;
        ctx.strokeRect(70, cardY, 940, 160);

        ctx.fillStyle = '#E8A33D';
        ctx.font = 'bold 20px system-ui, sans-serif';
        ctx.fillText(`0${idx + 1}`, 105, cardY + 50);

        ctx.fillStyle = '#F2F1ED';
        ctx.font = '20px system-ui, sans-serif';
        wrapText(ctx, item, 160, cardY + 50, 810, 32);

        cardY += 190;
      });

      // Call To Action Box
      ctx.fillStyle = 'rgba(232, 163, 61, 0.1)';
      ctx.fillRect(70, 930, 940, 180);
      ctx.strokeStyle = '#E8A33D';
      ctx.lineWidth = 2;
      ctx.strokeRect(70, 930, 940, 180);

      ctx.fillStyle = '#E8A33D';
      ctx.font = 'bold 24px system-ui, sans-serif';
      ctx.fillText('📌 Save this post for future reference', 110, 990);

      ctx.fillStyle = '#94A3B8';
      ctx.font = '18px system-ui, sans-serif';
      ctx.fillText('Follow along for more visual breakdowns on technology, science, and history.', 110, 1040);

      // Branding Bottom
      ctx.fillStyle = '#8B8D93';
      ctx.font = '16px system-ui, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('Created with ExplainIT • Grounded Visual AI Storytelling', 540, 1260);
      ctx.textAlign = 'left';
    }

    return canvas;
  };

  // 3. Download Carousel PDF (5-page 1080x1350 multi-page PDF)
  const handleDownloadCarouselPdf = async () => {
    setIsGeneratingPdf(true);
    setPdfSuccess(false);

    try {
      const pdf = new jsPDF({
        orientation: 'portrait',
        unit: 'px',
        format: [1080, 1350],
      });

      for (let i = 0; i < totalSlides; i++) {
        const slideCanvas = await renderSlideCanvas(i);
        const imgData = slideCanvas.toDataURL('image/jpeg', 0.95);
        if (i > 0) {
          pdf.addPage([1080, 1350], 'portrait');
        }
        pdf.addImage(imgData, 'JPEG', 0, 0, 1080, 1350);
      }

      const cleanName = topic.replace(/[^a-zA-Z0-9]/g, '_');
      pdf.save(`${cleanName}_LinkedIn_Carousel.pdf`);
      setPdfSuccess(true);
      setTimeout(() => setPdfSuccess(false), 3000);
    } catch (err) {
      console.error('Failed to generate Carousel PDF:', err);
    } finally {
      setIsGeneratingPdf(false);
    }
  };

  // 4. Download Full Vertical Infographic Poster (PNG)
  const handleDownloadPosterPng = async () => {
    setIsGeneratingPoster(true);
    setPosterSuccess(false);

    try {
      const posterCanvas = document.createElement('canvas');
      posterCanvas.width = 1080;
      posterCanvas.height = 3600;
      const ctx = posterCanvas.getContext('2d');

      // Background
      ctx.fillStyle = '#0F1117';
      ctx.fillRect(0, 0, 1080, 3600);

      // Poster Header
      ctx.fillStyle = '#E8A33D';
      ctx.font = 'bold 24px system-ui, sans-serif';
      ctx.fillText('EXPLAINIT INFOGRAPHIC', 80, 100);

      ctx.fillStyle = '#F2F1ED';
      ctx.font = 'bold 56px system-ui, serif';
      wrapText(ctx, topic, 80, 180, 920, 68);

      // Render all 3 panels sequentially
      let currentY = 320;
      for (let i = 0; i < panels.length; i++) {
        const panel = panels[i];
        
        // Step Badge
        ctx.fillStyle = 'rgba(232, 163, 61, 0.15)';
        ctx.fillRect(80, currentY, 140, 36);
        ctx.strokeStyle = '#E8A33D';
        ctx.lineWidth = 1.5;
        ctx.strokeRect(80, currentY, 140, 36);
        ctx.fillStyle = '#E8A33D';
        ctx.font = 'bold 15px system-ui, sans-serif';
        ctx.fillText(`STEP ${i + 1} OF 3`, 100, currentY + 24);

        currentY += 50;

        // Draw image
        if (panel?.image_url) {
          try {
            const img = await loadImage(panel.image_url);
            ctx.drawImage(img, 80, currentY, 920, 920);
            ctx.strokeStyle = '#262930';
            ctx.lineWidth = 2;
            ctx.strokeRect(80, currentY, 920, 920);
          } catch (e) {
            ctx.fillStyle = '#161B26';
            ctx.fillRect(80, currentY, 920, 920);
          }
        }

        currentY += 940;

        // Caption
        ctx.fillStyle = '#F2F1ED';
        ctx.font = '22px system-ui, serif';
        currentY = wrapText(ctx, panel?.caption || '', 80, currentY, 920, 34);
        currentY += 50;
      }

      // Poster Footer
      ctx.fillStyle = '#8B8D93';
      ctx.font = '16px system-ui, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('Generated by ExplainIT • Fact-Checked AI Visual Storyboard', 540, 3540);

      const dataUrl = posterCanvas.toDataURL('image/png');
      const link = document.createElement('a');
      link.download = `${topic.replace(/[^a-zA-Z0-9]/g, '_')}_Infographic.png`;
      link.href = dataUrl;
      link.click();

      setPosterSuccess(true);
      setTimeout(() => setPosterSuccess(false), 3000);
    } catch (err) {
      console.error('Failed to generate Infographic poster:', err);
    } finally {
      setIsGeneratingPoster(false);
    }
  };

  // 5. Copy LinkedIn Formatted Post Text
  const handleCopyPostText = () => {
    if (!postCopy) return;

    const fullText = [
      postCopy.hook,
      '',
      ...(postCopy.takeaways || []),
      '',
      postCopy.cta,
      '',
      (postCopy.hashtags || []).join(' ')
    ].join('\n');

    navigator.clipboard.writeText(fullText);
    setCopySuccess(true);
    setTimeout(() => setCopySuccess(false), 2500);
  };

  // 6. Direct Post via existing LinkedIn API
  const handleDirectPostActivePanel = async () => {
    const activePanelNum = Math.min(Math.max(currentSlide, 1), panels.length);
    const caption = panels[activePanelNum - 1]?.caption || topic;

    setDirectPosting(true);
    try {
      if (onDirectPost) {
        await onDirectPost(activePanelNum, caption);
        setDirectPostSuccess(true);
        setTimeout(() => setDirectPostSuccess(false), 3000);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setDirectPosting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 bg-[#0B0C0E]/90 backdrop-blur-md flex items-center justify-center p-3 sm:p-6 overflow-y-auto">
      <motion.div
        initial={{ opacity: 0, scale: 0.96 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.96 }}
        className="relative w-full max-w-6xl bg-[#15171A] border border-border-dark rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[94vh]"
      >
        {/* Modal Top Bar */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border-dark bg-[#0F1117]">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-[#0077B5]/20 border border-[#0077B5]/40 flex items-center justify-center text-[#0077B5]">
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                <path d="M19 0h-14c-2.761 0-5 2.239-5 5v14c0 2.761 2.239 5 5 5h14c2.762 0 5-2.239 5-5v-14c0-2.761-2.238-5-5-5zm-11 19h-3v-11h3v11zm-1.5-12.268c-.966 0-1.75-.79-1.75-1.764s.784-1.764 1.75-1.764 1.75.79 1.75 1.764-.783 1.764-1.75 1.764zm13.5 12.268h-3v-5.604c0-3.368-4-3.113-4 0v5.604h-3v-11h3v1.765c1.396-2.586 7-2.777 7 2.476v6.759z"/>
              </svg>
            </div>
            <div>
              <h3 className="text-base font-bold text-text-primary flex items-center gap-2">
                LinkedIn Carousel &amp; Share Studio
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-accent/20 text-accent font-semibold uppercase">Viral Ready</span>
              </h3>
              <p className="text-xs text-text-muted">Turn your 3-panel explanation into a swipeable document carousel or high-res infographic.</p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-2 rounded-lg bg-[#262930] text-text-muted hover:text-text-primary transition-colors cursor-pointer"
            title="Close Studio"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Modal Body: Split 2-Column Layout */}
        <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 overflow-y-auto">
          
          {/* Left Column (7 cols): Interactive Carousel Slide Viewer */}
          <div className="lg:col-span-7 p-6 border-b lg:border-b-0 lg:border-r border-border-dark flex flex-col items-center justify-between bg-[#0F1117]/60">
            
            {/* Slide Header */}
            <div className="w-full flex items-center justify-between mb-4 text-xs">
              <span className="font-semibold text-accent uppercase tracking-wider">
                Slide {currentSlide + 1} of {totalSlides}
              </span>
              <span className="text-text-muted">4:5 Aspect Ratio (LinkedIn Standard)</span>
            </div>

            {/* Simulated Carousel Slide Frame */}
            <div className="relative w-full max-w-sm aspect-[4/5] rounded-xl border border-border-dark bg-[#15171A] shadow-xl overflow-hidden p-4 flex flex-col justify-between">
              
              {/* Slide Brand Tag */}
              <div className="flex items-center justify-between text-[11px] pb-2 border-b border-border-dark/60">
                <span className="font-bold text-accent tracking-wide">EXPLAINIT</span>
                <span className="text-text-muted">{currentSlide + 1}/{totalSlides}</span>
              </div>

              {/* Slide Content by Index */}
              <div className="flex-1 flex flex-col items-center justify-center my-2 text-center overflow-hidden">
                {currentSlide === 0 ? (
                  // Cover Slide
                  <div className="flex flex-col items-center justify-center h-full px-2 space-y-4">
                    <span className="text-[10px] uppercase font-bold tracking-widest px-2.5 py-1 rounded-full border border-accent/40 bg-accent/10 text-accent">
                      3-Step Breakdown
                    </span>
                    <h4 className="font-fraunces text-2xl font-bold text-text-primary leading-tight">
                      {topic}
                    </h4>
                    <p className="text-xs text-text-muted leading-relaxed">
                      A visual, fact-checked explainer backed by real source data.
                    </p>
                    <div className="pt-4 flex items-center gap-1.5 text-xs text-accent font-medium">
                      <span>Swipe to start</span>
                      <span>→</span>
                    </div>
                  </div>
                ) : currentSlide >= 1 && currentSlide <= panels.length ? (
                  // Panel Slides
                  <div className="w-full h-full flex flex-col items-center justify-between">
                    <span className="text-[10px] font-bold text-accent mb-1 uppercase tracking-wider">
                      Step {currentSlide} of 3
                    </span>
                    <div className="w-full flex-1 rounded-lg overflow-hidden border border-border-dark bg-[#0F1117] flex items-center justify-center">
                      <img
                        src={panels[currentSlide - 1]?.image_url}
                        alt={`Step ${currentSlide}`}
                        className="w-full h-full object-contain"
                      />
                    </div>
                    <p className="text-xs text-text-primary font-medium mt-2 line-clamp-3 leading-snug px-1">
                      {panels[currentSlide - 1]?.caption}
                    </p>
                  </div>
                ) : (
                  // Summary Slide
                  <div className="w-full h-full flex flex-col justify-between text-left p-1">
                    <div>
                      <span className="text-[10px] font-bold text-green-400 uppercase tracking-wider">
                        Key Takeaways
                      </span>
                      <h4 className="font-fraunces text-lg font-bold text-text-primary mt-1 mb-2">
                        Core Learnings
                      </h4>
                      <div className="space-y-2">
                        {panels.slice(0, 3).map((p, i) => (
                          <div key={i} className="p-2 rounded bg-[#0F1117] border border-border-dark text-[11px] text-text-primary">
                            <span className="text-accent font-bold mr-1">0{i + 1}</span> {p.caption}
                          </div>
                        ))}
                      </div>
                    </div>
                    <div className="p-2 rounded bg-accent/10 border border-accent/30 text-center">
                      <p className="text-[11px] font-semibold text-accent">📌 Save &amp; Share this post</p>
                    </div>
                  </div>
                )}
              </div>

              {/* Slide Footer */}
              <div className="pt-2 border-t border-border-dark/60 text-[10px] text-text-muted flex justify-between items-center">
                <span>Verified Fact-Checked</span>
                <span>ExplainIT AI</span>
              </div>
            </div>

            {/* Slide Navigation Controls */}
            <div className="flex items-center gap-4 mt-4">
              <button
                onClick={() => setCurrentSlide(prev => Math.max(0, prev - 1))}
                disabled={currentSlide === 0}
                className={`p-2 rounded-full border transition-colors ${
                  currentSlide === 0 ? 'border-border-dark/40 text-border-dark cursor-not-allowed' : 'border-border-dark text-text-muted hover:text-text-primary hover:bg-[#262930] cursor-pointer'
                }`}
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
              </button>

              <div className="flex items-center gap-2">
                {Array.from({ length: totalSlides }).map((_, i) => (
                  <button
                    key={i}
                    onClick={() => setCurrentSlide(i)}
                    className={`w-2.5 h-2.5 rounded-full transition-all cursor-pointer ${
                      i === currentSlide ? 'bg-accent scale-125' : 'bg-[#262930] hover:bg-text-muted'
                    }`}
                  />
                ))}
              </div>

              <button
                onClick={() => setCurrentSlide(prev => Math.min(totalSlides - 1, prev + 1))}
                disabled={currentSlide === totalSlides - 1}
                className={`p-2 rounded-full border transition-colors ${
                  currentSlide === totalSlides - 1 ? 'border-border-dark/40 text-border-dark cursor-not-allowed' : 'border-border-dark text-text-muted hover:text-text-primary hover:bg-[#262930] cursor-pointer'
                }`}
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </button>
            </div>
          </div>

          {/* Right Column (5 cols): Download & Share Actions */}
          <div className="lg:col-span-5 p-6 flex flex-col justify-between space-y-6">
            
            {/* Top Section: Export Buttons */}
            <div className="space-y-4">
              <h4 className="text-xs font-bold text-text-muted uppercase tracking-wider">Export Formats</h4>
              
              {/* PRIMARY: Download Carousel PDF */}
              <button
                onClick={handleDownloadCarouselPdf}
                disabled={isGeneratingPdf}
                className="w-full flex items-center justify-between p-3.5 rounded-xl border border-accent/60 bg-accent/10 hover:bg-accent hover:text-charcoal text-text-primary font-semibold text-sm transition-all duration-300 cursor-pointer shadow-lg group"
              >
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-accent/20 group-hover:bg-charcoal/20 flex items-center justify-center text-accent group-hover:text-charcoal transition-colors">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                  </div>
                  <div className="text-left">
                    <p className="leading-snug">Download Carousel PDF</p>
                    <p className="text-[11px] font-normal text-text-muted group-hover:text-charcoal/80">5-slide PDF for LinkedIn Documents</p>
                  </div>
                </div>

                {isGeneratingPdf ? (
                  <div className="w-4 h-4 border-2 border-accent group-hover:border-charcoal border-t-transparent animate-spin rounded-full" />
                ) : pdfSuccess ? (
                  <span className="text-xs text-green-400 font-bold">✓ Ready</span>
                ) : (
                  <span className="text-xs opacity-60">↓</span>
                )}
              </button>

              {/* SECONDARY: Download Infographic Poster (PNG) */}
              <button
                onClick={handleDownloadPosterPng}
                disabled={isGeneratingPoster}
                className="w-full flex items-center justify-between p-3.5 rounded-xl border border-border-dark bg-surface hover:border-accent/40 text-text-primary text-sm font-semibold transition-all cursor-pointer group"
              >
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-[#262930] flex items-center justify-center text-text-muted group-hover:text-accent transition-colors">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                    </svg>
                  </div>
                  <div className="text-left">
                    <p className="leading-snug">Download Infographic Poster</p>
                    <p className="text-[11px] font-normal text-text-muted">Vertical high-res composite PNG</p>
                  </div>
                </div>

                {isGeneratingPoster ? (
                  <div className="w-4 h-4 border-2 border-text-muted border-t-accent animate-spin rounded-full" />
                ) : posterSuccess ? (
                  <span className="text-xs text-green-400 font-bold">✓ Saved</span>
                ) : (
                  <span className="text-xs text-text-muted">↓</span>
                )}
              </button>
            </div>

            {/* Middle Section: AI Generated LinkedIn Post Copy */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold text-text-muted uppercase tracking-wider flex items-center gap-1.5">
                  <span>AI Post Caption &amp; Hook</span>
                  {loadingCopy && <div className="w-2.5 h-2.5 border-2 border-accent border-t-transparent animate-spin rounded-full" />}
                </h4>
                <button
                  onClick={handleCopyPostText}
                  className="text-xs font-semibold text-accent hover:underline cursor-pointer flex items-center gap-1"
                >
                  {copySuccess ? '✓ Copied!' : 'Copy Text'}
                </button>
              </div>

              <div className="p-3 rounded-xl bg-[#0F1117] border border-border-dark text-xs text-text-primary/90 space-y-2 max-h-40 overflow-y-auto leading-relaxed select-text font-sans">
                <p className="font-semibold text-accent">{postCopy?.hook}</p>
                <div className="space-y-1 text-text-muted">
                  {(postCopy?.takeaways || []).map((t, idx) => (
                    <p key={idx}>{t}</p>
                  ))}
                </div>
                <p className="text-text-primary/80">{postCopy?.cta}</p>
                <p className="text-[#38BDF8] text-[11px]">{(postCopy?.hashtags || []).join(' ')}</p>
              </div>
            </div>

            {/* Bottom Section: Pro Posting Tip & Direct Post */}
            <div className="pt-3 border-t border-border-dark space-y-3">
              <div className="p-2.5 rounded-lg bg-[#262930]/40 border border-border-dark text-[11px] text-text-muted leading-relaxed">
                <span className="font-bold text-accent mr-1">💡 How to post:</span>
                Download the Carousel PDF above, head over to LinkedIn, create a post, click the <span className="text-text-primary font-semibold">Document 📄</span> button, and paste your copied caption!
              </div>

              {/* Direct Post Button (Single Panel fallback) */}
              <div className="flex items-center justify-between">
                {linkedinConnected ? (
                  <button
                    onClick={handleDirectPostActivePanel}
                    disabled={directPosting}
                    className="w-full py-2.5 px-4 rounded-xl border border-border-dark bg-[#0077B5]/20 hover:bg-[#0077B5]/30 text-xs font-medium text-text-primary flex items-center justify-center gap-2 cursor-pointer transition-colors"
                  >
                    <svg className="w-3.5 h-3.5 text-[#0077B5]" fill="currentColor" viewBox="0 0 24 24">
                      <path d="M19 0h-14c-2.761 0-5 2.239-5 5v14c0 2.761 2.239 5 5 5h14c2.762 0 5-2.239 5-5v-14c0-2.761-2.238-5-5-5zm-11 19h-3v-11h3v11zm-1.5-12.268c-.966 0-1.75-.79-1.75-1.764s.784-1.764 1.75-1.764 1.75.79 1.75 1.764-.783 1.764-1.75 1.764zm13.5 12.268h-3v-5.604c0-3.368-4-3.113-4 0v5.604h-3v-11h3v1.765c1.396-2.586 7-2.777 7 2.476v6.759z"/>
                    </svg>
                    {directPosting ? 'Publishing...' : directPostSuccess ? '✓ Published to LinkedIn!' : `Direct Post Slide ${currentSlide + 1} to LinkedIn`}
                  </button>
                ) : (
                  <button
                    onClick={onConnectLinkedin}
                    className="w-full py-2 px-3 rounded-lg border border-border-dark text-[11px] text-text-muted hover:text-text-primary transition-colors cursor-pointer text-center"
                  >
                    Connect LinkedIn account for 1-click publishing
                  </button>
                )}
              </div>
            </div>

          </div>
        </div>
      </motion.div>
    </div>
  );
}

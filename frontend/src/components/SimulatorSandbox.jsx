import { useState, useEffect, useRef, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

export default function SimulatorSandbox({ topic, panels, onClose }) {
  const [simulationData, setSimulationData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [params, setParams] = useState({});
  const [isPlaying, setIsPlaying] = useState(true);
  const [activePreset, setActivePreset] = useState(null);
  const [hoveredNode, setHoveredNode] = useState(null);

  const canvasRef = useRef(null);
  const animFrameRef = useRef(null);
  const particlesRef = useRef([]);
  const pulseRipplesRef = useRef([]);

  // 1. Fetch simulation configuration from backend
  useEffect(() => {
    let isMounted = true;
    const fetchSimulation = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch('http://localhost:8000/generate-simulation', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ topic, panels: panels || [] }),
        });
        if (!res.ok) throw new Error('Failed to generate simulation');
        const data = await res.json();
        if (isMounted) {
          setSimulationData(data);
          // Initialize parameter values from defaults
          const initialParams = {};
          (data.controls || []).forEach(ctrl => {
            initialParams[ctrl.id] = ctrl.default ?? 50;
          });
          setParams(initialParams);
          if (data.presets && data.presets.length > 0) {
            setActivePreset(data.presets[0].name);
          }
        }
      } catch (err) {
        console.error('Error loading simulation:', err);
        if (isMounted) setError(err.message);
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    fetchSimulation();
    return () => { isMounted = false; };
  }, [topic, panels]);

  // Safe Math formula evaluator
  const evaluateExpression = (exprString, currentParams) => {
    try {
      let expr = exprString || '0';
      Object.keys(currentParams).forEach(k => {
        const reg = new RegExp(`\\b${k}\\b`, 'g');
        expr = expr.replace(reg, Number(currentParams[k]) || 0);
      });
      // Restricted Function invocation with Math scope
      const res = Function('Math', `"use strict"; return (${expr});`)(Math);
      return typeof res === 'number' && !isNaN(res) ? res : 0;
    } catch (e) {
      return 0;
    }
  };

  const evaluateCondition = (condString, currentParams) => {
    try {
      let expr = condString;
      Object.keys(currentParams).forEach(k => {
        const reg = new RegExp(`\\b${k}\\b`, 'g');
        expr = expr.replace(reg, Number(currentParams[k]) || 0);
      });
      return Boolean(Function(`"use strict"; return (${expr});`)());
    } catch (e) {
      return false;
    }
  };

  // 2. Computed Metrics and Active Live Insight
  const computedMetrics = useMemo(() => {
    if (!simulationData?.metrics) return [];
    return simulationData.metrics.map(m => {
      const val = evaluateExpression(m.formula_js, params);
      return {
        ...m,
        value: typeof val === 'number' ? val.toFixed(1) : val,
        raw: val,
      };
    });
  }, [simulationData, params]);

  const activeInsight = useMemo(() => {
    if (!simulationData?.live_insights) return null;
    for (const insight of simulationData.live_insights) {
      if (evaluateCondition(insight.condition_js, params)) {
        return insight.text;
      }
    }
    return 'System operating in dynamic equilibrium. Parameters are within normal operational limits.';
  }, [simulationData, params]);

  // 3. Preset selector
  const handleSelectPreset = (preset) => {
    setActivePreset(preset.name);
    setParams(prev => ({ ...prev, ...(preset.values || {}) }));
  };

  // Slider change handler
  const handleParamChange = (id, val) => {
    setActivePreset(null);
    setParams(prev => ({ ...prev, [id]: Number(val) }));
  };

  // 4. HTML5 Canvas 60 FPS Particle & Node Physics Engine
  useEffect(() => {
    if (!simulationData || loading) return;

    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    // Resize canvas to match display size
    const resizeCanvas = () => {
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      ctx.scale(dpr, dpr);
    };
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    // Initialize particles pool
    const nodeMap = {};
    (simulationData.nodes || []).forEach(n => { nodeMap[n.id] = n; });

    const totalParticles = 65;
    particlesRef.current = [];
    for (let i = 0; i < totalParticles; i++) {
      const flow = simulationData.flows?.[i % (simulationData.flows?.length || 1)];
      particlesRef.current.push({
        flow,
        progress: Math.random(),
        size: Math.random() * 2.5 + 2,
        offset: (Math.random() - 0.5) * 16,
      });
    }

    // Animation Loop
    let lastTime = performance.now();

    const render = (now) => {
      const dt = Math.min((now - lastTime) / 1000, 0.1);
      lastTime = now;

      const rect = canvas.getBoundingClientRect();
      const w = rect.width;
      const h = rect.height;

      ctx.clearRect(0, 0, w, h);

      // Draw subtle background grid
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.03)';
      ctx.lineWidth = 1;
      const gridSize = 40;
      for (let x = 0; x < w; x += gridSize) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, h);
        ctx.stroke();
      }
      for (let y = 0; y < h; y += gridSize) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(w, y);
        ctx.stroke();
      }

      // 1. Draw Flow Streams (Connecting Bezier Curves)
      (simulationData.flows || []).forEach(flow => {
        const fromNode = nodeMap[flow.from_node];
        const toNode = nodeMap[flow.to_node];
        if (!fromNode || !toNode) return;

        const x1 = (fromNode.x / 100) * w;
        const y1 = (fromNode.y / 100) * h;
        const x2 = (toNode.x / 100) * w;
        const y2 = (toNode.y / 100) * h;
        const cx = (x1 + x2) / 2;
        const cy = (y1 + y2) / 2 - 25;

        // Flow baseline track
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.quadraticCurveTo(cx, cy, x2, y2);
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.08)';
        ctx.lineWidth = 3;
        ctx.stroke();

        // Glow stream
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.quadraticCurveTo(cx, cy, x2, y2);
        ctx.strokeStyle = (flow.color || '#E8A33D') + '22';
        ctx.lineWidth = 6;
        ctx.stroke();
      });

      // 2. Animate and Render Particles
      if (isPlaying) {
        particlesRef.current.forEach(p => {
          const flow = p.flow;
          if (!flow) return;
          const fromNode = nodeMap[flow.from_node];
          const toNode = nodeMap[flow.to_node];
          if (!fromNode || !toNode) return;

          // Compute flow speed based on controlling slider parameter
          const paramVal = flow.speed_multiplier_param ? (params[flow.speed_multiplier_param] ?? 50) : 50;
          const speedFactor = Math.max(0.08, paramVal / 65);
          p.progress += dt * 0.35 * speedFactor;

          if (p.progress >= 1) {
            p.progress = 0;
            // Spawn node pulse ripple at destination
            pulseRipplesRef.current.push({
              x: (toNode.x / 100) * w,
              y: (toNode.y / 100) * h,
              radius: 12,
              maxRadius: 36,
              alpha: 0.6,
              color: flow.color || '#E8A33D',
            });
          }

          const t = p.progress;
          const x1 = (fromNode.x / 100) * w;
          const y1 = (fromNode.y / 100) * h;
          const x2 = (toNode.x / 100) * w;
          const y2 = (toNode.y / 100) * h;
          const cx = (x1 + x2) / 2;
          const cy = (y1 + y2) / 2 - 25;

          // Quadratic Bezier interpolation
          const px = (1 - t) * (1 - t) * x1 + 2 * (1 - t) * t * cx + t * t * x2;
          const py = (1 - t) * (1 - t) * y1 + 2 * (1 - t) * t * cy + t * t * y2;

          // Draw Glowing Particle
          ctx.beginPath();
          ctx.arc(px, py + p.offset * (1 - Math.abs(t - 0.5) * 2), p.size, 0, Math.PI * 2);
          ctx.fillStyle = flow.color || '#E8A33D';
          ctx.shadowColor = flow.color || '#E8A33D';
          ctx.shadowBlur = 8;
          ctx.fill();
          ctx.shadowBlur = 0;
        });
      }

      // 3. Render and Update Pulse Ripples
      pulseRipplesRef.current.forEach((r, idx) => {
        r.radius += dt * 45;
        r.alpha -= dt * 1.2;
        if (r.alpha > 0) {
          ctx.beginPath();
          ctx.arc(r.x, r.y, r.radius, 0, Math.PI * 2);
          ctx.strokeStyle = r.color;
          ctx.globalAlpha = Math.max(0, r.alpha);
          ctx.lineWidth = 2;
          ctx.stroke();
          ctx.globalAlpha = 1.0;
        }
      });
      pulseRipplesRef.current = pulseRipplesRef.current.filter(r => r.alpha > 0);

      // 4. Render Nodes
      (simulationData.nodes || []).forEach(node => {
        const nx = (node.x / 100) * w;
        const ny = (node.y / 100) * h;
        const isHovered = hoveredNode === node.id;
        const baseRadius = 26;
        const radius = isHovered ? baseRadius + 4 : baseRadius;

        // Outer Glow halo
        ctx.beginPath();
        ctx.arc(nx, ny, radius + 10, 0, Math.PI * 2);
        ctx.fillStyle = (node.color || '#E8A33D') + '15';
        ctx.fill();

        // Node Body
        ctx.beginPath();
        ctx.arc(nx, ny, radius, 0, Math.PI * 2);
        ctx.fillStyle = '#15171A';
        ctx.fill();
        ctx.lineWidth = isHovered ? 3 : 2;
        ctx.strokeStyle = node.color || '#E8A33D';
        ctx.stroke();

        // Center Indicator Core
        ctx.beginPath();
        ctx.arc(nx, ny, 7, 0, Math.PI * 2);
        ctx.fillStyle = node.color || '#E8A33D';
        ctx.shadowColor = node.color || '#E8A33D';
        ctx.shadowBlur = 10;
        ctx.fill();
        ctx.shadowBlur = 0;

        // Node Label Typography
        ctx.font = 'bold 13px system-ui, sans-serif';
        ctx.fillStyle = '#F2F1ED';
        ctx.textAlign = 'center';
        ctx.fillText(node.label, nx, ny + radius + 18);

        // Node Subtitle / Role
        ctx.font = '10px system-ui, sans-serif';
        ctx.fillStyle = '#8B8D93';
        ctx.fillText(node.role || '', nx, ny + radius + 32);
      });

      animFrameRef.current = requestAnimationFrame(render);
    };

    animFrameRef.current = requestAnimationFrame(render);

    return () => {
      window.removeEventListener('resize', resizeCanvas);
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    };
  }, [simulationData, loading, params, isPlaying, hoveredNode]);

  // Canvas mouse interaction for node hover
  const handleCanvasMouseMove = (e) => {
    if (!canvasRef.current || !simulationData?.nodes) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    let found = null;
    simulationData.nodes.forEach(node => {
      const nx = (node.x / 100) * rect.width;
      const ny = (node.y / 100) * rect.height;
      const dist = Math.hypot(mx - nx, my - ny);
      if (dist <= 30) found = node.id;
    });
    setHoveredNode(found);
  };

  return (
    <div className="w-full max-w-7xl mx-auto flex flex-col items-center">
      {/* Top Header Bar */}
      <div className="w-full flex justify-between items-center mb-6 flex-wrap gap-4">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2.5 bg-surface px-4 py-1.5 rounded-full border border-border-dark shadow-sm">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#10B981] opacity-60"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-[#10B981] shadow-[0_0_8px_rgba(16,185,129,0.8)]"></span>
            </span>
            <span className="text-[10px] tracking-[0.2em] uppercase text-text-primary font-bold">Concept Simulator</span>
            <span className="text-border-dark">|</span>
            <span className="text-xs text-text-muted capitalize font-medium">{topic}</span>
          </div>

          <span className="text-[11px] px-2.5 py-1 rounded-full bg-[#E8A33D]/10 text-accent border border-accent/20 font-medium">
            ● 60 FPS Particle Physics
          </span>
        </div>

        {/* Header Actions */}
        <div className="flex items-center gap-3">
          <button
            onClick={() => setIsPlaying(p => !p)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border-dark bg-surface hover:bg-surface/80 text-xs font-medium text-text-primary transition-colors cursor-pointer"
          >
            {isPlaying ? (
              <>
                <svg className="w-3.5 h-3.5 text-accent" fill="currentColor" viewBox="0 0 24 24"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
                <span>Pause</span>
              </>
            ) : (
              <>
                <svg className="w-3.5 h-3.5 text-[#10B981]" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                <span>Resume</span>
              </>
            )}
          </button>

          <button
            onClick={() => {
              if (simulationData?.controls) {
                const reset = {};
                simulationData.controls.forEach(c => { reset[c.id] = c.default ?? 50; });
                setParams(reset);
                setActivePreset(null);
              }
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border-dark bg-surface hover:bg-surface/80 text-xs font-medium text-text-muted hover:text-text-primary transition-colors cursor-pointer"
            title="Reset parameters to defaults"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
            <span>Reset</span>
          </button>

          <div className="h-4 w-[1px] bg-border-dark hidden sm:block" />

          {/* Close / Return to Comic Reader */}
          <button
            onClick={onClose}
            className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-accent text-charcoal font-semibold text-xs transition-all shadow-sm cursor-pointer hover:brightness-110"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18"/></svg>
            <span>Back to Storyboard</span>
          </button>
        </div>
      </div>

      {/* Main Sandbox Frame */}
      {loading ? (
        <div className="w-full aspect-[16/9] min-h-[500px] rounded-2xl border border-border-dark bg-surface flex flex-col items-center justify-center p-8 gap-4 shadow-2xl">
          <div className="relative flex items-center justify-center">
            <div className="w-16 h-16 rounded-full border-4 border-border-dark border-t-accent animate-spin" />
            <div className="absolute w-8 h-8 rounded-full bg-accent/20 animate-pulse" />
          </div>
          <div className="text-center space-y-1">
            <h4 className="text-sm font-bold text-text-primary tracking-wide">Synthesizing Physics &amp; Logic Simulation...</h4>
            <p className="text-xs text-text-muted">Analyzing state transitions, rate equations, and particle streams for {topic}</p>
          </div>
        </div>
      ) : error ? (
        <div className="w-full p-8 rounded-2xl border border-red-500/30 bg-red-500/10 text-center space-y-3">
          <p className="text-sm text-red-300 font-medium">{error}</p>
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg bg-surface border border-border-dark text-xs text-text-primary"
          >
            Return to Storyboard
          </button>
        </div>
      ) : (
        <div className="w-full grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">
          
          {/* Left Canvas Sandbox (8 cols) */}
          <div className="lg:col-span-8 flex flex-col gap-4">
            <div className="relative w-full aspect-[16/10] min-h-[460px] rounded-2xl border border-border-dark bg-[#0B0C0E] overflow-hidden shadow-2xl flex items-center justify-center">
              
              {/* Interactive Canvas */}
              <canvas
                ref={canvasRef}
                onMouseMove={handleCanvasMouseMove}
                onMouseLeave={() => setHoveredNode(null)}
                className="w-full h-full cursor-crosshair select-none block"
              />

              {/* Top Banner on Canvas */}
              <div className="absolute top-4 left-4 right-4 flex items-center justify-between pointer-events-none">
                <div className="px-3 py-1.5 rounded-lg bg-[#15171A]/80 backdrop-blur-md border border-border-dark text-xs text-text-muted shadow-sm">
                  <span className="font-semibold text-text-primary">{simulationData?.title}</span>
                </div>
                <div className="px-2.5 py-1 rounded-lg bg-[#15171A]/80 backdrop-blur-md border border-border-dark text-[11px] text-accent font-medium">
                  {isPlaying ? 'Simulation Running' : 'Simulation Paused'}
                </div>
              </div>

              {/* Bottom Particle Legend */}
              <div className="absolute bottom-4 left-4 flex items-center gap-4 px-3 py-1.5 rounded-lg bg-[#15171A]/80 backdrop-blur-md border border-border-dark text-[11px] pointer-events-none">
                {(simulationData?.flows || []).map((f, i) => (
                  <div key={i} className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full" style={{ backgroundColor: f.color }} />
                    <span className="text-text-muted">{f.particle_name}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Dynamic AI Live Insight Callout */}
            <AnimatePresence mode="wait">
              <motion.div
                key={activeInsight}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                className="p-4 rounded-xl border border-accent/30 bg-accent/5 backdrop-blur-sm flex items-start gap-3 shadow-sm"
              >
                <div className="p-1.5 rounded-lg bg-accent/10 border border-accent/30 text-accent shrink-0 mt-0.5">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <div className="space-y-0.5">
                  <h5 className="text-xs font-bold text-accent uppercase tracking-wider">Dynamic System Observation</h5>
                  <p className="text-xs text-text-primary/90 leading-relaxed font-sans">{activeInsight}</p>
                </div>
              </motion.div>
            </AnimatePresence>
          </div>

          {/* Right Control Deck (4 cols) */}
          <div className="lg:col-span-4 flex flex-col gap-4">
            
            {/* 1. Experimental Scenario Presets */}
            {simulationData?.presets && simulationData.presets.length > 0 && (
              <div className="p-4 rounded-xl border border-border-dark bg-surface shadow-sm space-y-2.5">
                <span className="text-[11px] font-bold text-text-muted uppercase tracking-wider block">
                  Experimental Scenarios
                </span>
                <div className="grid grid-cols-1 gap-2">
                  {simulationData.presets.map((preset, idx) => {
                    const isSelected = activePreset === preset.name;
                    return (
                      <button
                        key={idx}
                        onClick={() => handleSelectPreset(preset)}
                        className={`p-2.5 rounded-lg border text-left transition-all cursor-pointer ${
                          isSelected
                            ? 'border-accent bg-accent/10 shadow-sm'
                            : 'border-border-dark bg-[#0F1117] hover:border-text-muted hover:bg-[#15171A]'
                        }`}
                      >
                        <div className="flex items-center justify-between mb-0.5">
                          <span className={`text-xs font-semibold ${isSelected ? 'text-accent' : 'text-text-primary'}`}>
                            {preset.name}
                          </span>
                          {isSelected && <span className="text-[10px] text-accent font-bold">Active ✓</span>}
                        </div>
                        <p className="text-[11px] text-text-muted line-clamp-1 leading-snug">{preset.description}</p>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {/* 2. Interactive Parameter Sliders */}
            <div className="p-4 rounded-xl border border-border-dark bg-surface shadow-sm space-y-4 flex-1">
              <span className="text-[11px] font-bold text-text-muted uppercase tracking-wider block">
                Environmental Sliders
              </span>

              <div className="space-y-4">
                {(simulationData?.controls || []).map(ctrl => {
                  const val = params[ctrl.id] ?? ctrl.default ?? 50;
                  return (
                    <div key={ctrl.id} className="space-y-1.5">
                      <div className="flex items-center justify-between text-xs">
                        <label htmlFor={ctrl.id} className="font-medium text-text-primary">
                          {ctrl.label}
                        </label>
                        <span className="px-2 py-0.5 rounded bg-[#0F1117] border border-border-dark text-accent font-mono font-bold text-[11px]">
                          {val}{ctrl.unit || ''}
                        </span>
                      </div>

                      <input
                        id={ctrl.id}
                        type="range"
                        min={ctrl.min ?? 0}
                        max={ctrl.max ?? 100}
                        step={ctrl.step ?? 1}
                        value={val}
                        onChange={(e) => handleParamChange(ctrl.id, e.target.value)}
                        className="w-full accent-accent bg-[#0F1117] h-2 rounded-lg cursor-pointer transition-all"
                      />

                      {ctrl.description && (
                        <p className="text-[10px] text-text-muted leading-tight">{ctrl.description}</p>
                      )}
                    </div>
                  );
                })}
              </div>

              {/* 3. Live Calculated Outputs */}
              {computedMetrics.length > 0 && (
                <div className="pt-3 border-t border-border-dark space-y-2">
                  <span className="text-[10px] font-bold text-text-muted uppercase tracking-wider block">
                    Real-Time Rate Metrics
                  </span>
                  <div className="grid grid-cols-2 gap-2">
                    {computedMetrics.map(m => (
                      <div key={m.id} className="p-2 rounded-lg bg-[#0F1117] border border-border-dark text-center">
                        <span className="text-[10px] text-text-muted block truncate">{m.label}</span>
                        <span className="text-base font-bold text-text-primary font-mono block">
                          {m.value} <span className="text-[10px] text-accent font-sans font-normal">{m.unit}</span>
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

            </div>

          </div>
        </div>
      )}
    </div>
  );
}

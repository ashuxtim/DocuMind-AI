import { useEffect, useRef, useImperativeHandle, forwardRef, useCallback } from 'react';
import { Sigma } from 'sigma';
import EdgeCurveProgram from '@sigma/edge-curve';
import { MultiGraph } from 'graphology';
import FA2Layout from 'graphology-layout-forceatlas2/worker';
import forceAtlas2 from 'graphology-layout-forceatlas2';
import noverlap from 'graphology-layout-noverlap';

// ── Color helpers ──────────────────────────────────────────────────────────────
const hexToRgb = (hex) => {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return result
    ? { r: parseInt(result[1], 16), g: parseInt(result[2], 16), b: parseInt(result[3], 16) }
    : { r: 148, g: 163, b: 184 };
};

const rgbToHex = (r, g, b) =>
  '#' +
  [r, g, b]
    .map((x) => {
      const hex = Math.max(0, Math.min(255, Math.round(x))).toString(16);
      return hex.length === 1 ? '0' + hex : hex;
    })
    .join('');

const dimColor = (hex, amount) => {
  const rgb = hexToRgb(hex);
  const bg  = { r: 18, g: 18, b: 28 };
  return rgbToHex(
    bg.r + (rgb.r - bg.r) * amount,
    bg.g + (rgb.g - bg.g) * amount,
    bg.b + (rgb.b - bg.b) * amount,
  );
};

const brightenColor = (hex, factor) => {
  const rgb = hexToRgb(hex);
  return rgbToHex(
    rgb.r + ((255 - rgb.r) * (factor - 1)) / factor,
    rgb.g + ((255 - rgb.g) * (factor - 1)) / factor,
    rgb.b + ((255 - rgb.b) * (factor - 1)) / factor,
  );
};

// ── Layout helpers ─────────────────────────────────────────────────────────────
const NOVERLAP_SETTINGS = { maxIterations: 20, ratio: 1.1, margin: 10, expansion: 1.05 };

function getLayoutDuration(nodeCount) {
  if (nodeCount < 100)  return 5_000;
  if (nodeCount < 500)  return 10_000;
  if (nodeCount < 1000) return 15_000;
  return 20_000;
}

// ── Sigma settings ─────────────────────────────────────────────────────────────
const SIGMA_SETTINGS = {
  renderLabels: true,
  labelFont: 'JetBrains Mono, monospace',
  labelSize: 11,
  labelWeight: '500',
  labelColor: { color: '#e4e4ed' },
  labelRenderedSizeThreshold: 8,
  labelDensity: 0.1,
  labelGridCellSize: 70,
  defaultNodeColor: '#94A3B8',
  defaultEdgeColor: '#2a2a3a',
  defaultEdgeType: 'curved',
  edgeProgramClasses: { curved: EdgeCurveProgram },

  defaultDrawNodeHover: (context, data, settings) => {
    const label = data.label;
    if (!label) return;

    const size   = settings.labelSize || 11;
    const font   = settings.labelFont || 'JetBrains Mono, monospace';
    const weight = settings.labelWeight || '500';

    context.font = `${weight} ${size}px ${font}`;
    const textWidth = context.measureText(label).width;

    const nodeSize = data.size || 8;
    const x        = data.x;
    const y        = data.y - nodeSize - 10;
    const paddingX = 8;
    const paddingY = 5;
    const height   = size + paddingY * 2;
    const width    = textWidth + paddingX * 2;
    const radius   = 4;

    context.fillStyle = '#12121c';
    context.beginPath();
    if (context.roundRect) {
      context.roundRect(x - width / 2, y - height / 2, width, height, radius);
    } else {
      context.rect(x - width / 2, y - height / 2, width, height);
    }
    context.fill();

    context.strokeStyle = data.color || '#7c3aed';
    context.lineWidth   = 2;
    context.stroke();

    context.fillStyle    = '#f5f5f7';
    context.textAlign    = 'center';
    context.textBaseline = 'middle';
    context.fillText(label, x, y);

    context.beginPath();
    context.arc(data.x, data.y, nodeSize + 4, 0, Math.PI * 2);
    context.strokeStyle = data.color || '#7c3aed';
    context.lineWidth   = 2;
    context.globalAlpha = 0.5;
    context.stroke();
    context.globalAlpha = 1;
  },

  minCameraRatio: 0.002,
  maxCameraRatio: 50,
  hideEdgesOnMove: true,
  zIndex: true,
};

// ── Animation constants ────────────────────────────────────────────────────────
// 'search' → cyan expanding pulse ring (1.2s)
// 'click'  → purple oscillating glow ring (2.0s)
const ANIM_DURATION = { search: 1200, click: 2000 };

// ── Component ──────────────────────────────────────────────────────────────────
// ── BFS: compute set of node IDs reachable within N hops from a root ──────────
function bfsReachable(g, rootId, maxHops) {
  if (!g || !rootId || !g.hasNode(rootId)) return null;
  if (maxHops >= 4) return null; // 4+ means no restriction
  const visited = new Map(); // nodeId → hop distance
  const queue   = [{ id: rootId, depth: 0 }];
  visited.set(rootId, 0);
  while (queue.length > 0) {
    const { id, depth } = queue.shift();
    if (depth >= maxHops) continue;
    g.forEachNeighbor(id, (neighbor) => {
      if (!visited.has(neighbor)) {
        visited.set(neighbor, depth + 1);
        queue.push({ id: neighbor, depth: depth + 1 });
      }
    });
  }
  return visited;
}

const GraphExplorer = forwardRef(function GraphExplorer(
  { graph, search, activeTypes, onTypeCounts, onGraphReady, onNodeSelect, onNodeHover, onLayoutChange, depthFilter, activeEdgeTypes },
  ref,
) {
  const containerRef    = useRef(null);
  const overlayRef      = useRef(null); // animation overlay canvas
  const sigmaRef        = useRef(null);
  const graphRef        = useRef(null);
  const hoveredNodeRef  = useRef(null);
  const selectedNodeRef = useRef(null);
  const activeTypesRef     = useRef(activeTypes);
  const depthFilterRef      = useRef(depthFilter ?? 4);
  const activeEdgeTypesRef  = useRef(activeEdgeTypes);
  // Cached BFS result — recomputed when selection or depthFilter changes
  const bfsReachableRef     = useRef(null);

  // Layout refs
  const layoutRef        = useRef(null);
  const layoutTimeoutRef = useRef(null);

  // Animation refs
  const animationsRef    = useRef([]);   // active animation entries
  const rafRef           = useRef(null); // requestAnimationFrame handle

  // Stable callback refs
  const onNodeSelectRef   = useRef(onNodeSelect);
  const onNodeHoverRef    = useRef(onNodeHover);
  const onLayoutChangeRef = useRef(onLayoutChange);

  useEffect(() => { onNodeSelectRef.current   = onNodeSelect;   }, [onNodeSelect]);
  useEffect(() => { onNodeHoverRef.current    = onNodeHover;    }, [onNodeHover]);
  useEffect(() => { onLayoutChangeRef.current = onLayoutChange; }, [onLayoutChange]);

  // ── Animation draw loop ────────────────────────────────────────────────────
  // Stored in a ref so the rAF callback always calls the latest version.
  const drawLoopRef = useRef(null);

  const startDrawLoop = useCallback(() => {
    if (rafRef.current) return; // already running

    const tick = () => {
      const canvas = overlayRef.current;
      const sigma  = sigmaRef.current;
      if (!canvas || !sigma) { rafRef.current = null; return; }

      const ctx = canvas.getContext('2d');
      const now = performance.now();

      // Clear overlay
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Prune completed animations
      animationsRef.current = animationsRef.current.filter(
        (a) => now - a.startTime < ANIM_DURATION[a.type],
      );

      for (const anim of animationsRef.current) {
        const display = sigma.getNodeDisplayData(anim.nodeId);
        if (!display) continue;

        // Convert graph→viewport coordinates
        const vp = sigma.graphToViewport({ x: display.x, y: display.y });
        const t  = (now - anim.startTime) / ANIM_DURATION[anim.type]; // 0→1
        const dpr = window.devicePixelRatio || 1;
        const sx  = vp.x * dpr;
        const sy  = vp.y * dpr;

        if (anim.type === 'search') {
          // ── Cyan expanding pulse ring ──────────────────────────────────────
          // Two concentric rings, offset in time, for a double-ripple effect
          for (let wave = 0; wave < 2; wave++) {
            const wt = Math.max(0, t - wave * 0.25);
            if (wt <= 0 || wt >= 1) continue;
            const radius = (20 + wt * 60) * dpr;
            const alpha  = (1 - wt) * 0.7;
            ctx.beginPath();
            ctx.arc(sx, sy, radius, 0, Math.PI * 2);
            ctx.strokeStyle = `rgba(34, 211, 238, ${alpha})`; // #22D3EE cyan
            ctx.lineWidth   = 2 * dpr;
            ctx.stroke();
          }
        } else if (anim.type === 'click') {
          // ── Purple oscillating glow ring ───────────────────────────────────
          // Pulses ~3 times, fades out over full duration
          const pulseT   = t * Math.PI * 6;        // 3 full oscillations
          const pulse    = 0.5 + 0.5 * Math.sin(pulseT);
          const radius   = (22 + pulse * 14) * dpr;
          const alpha    = (1 - t) * 0.65;
          const glow     = anim.color || '#7c3aed';
          const rgbMatch = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(glow);
          const [rr, gg, bb] = rgbMatch
            ? [parseInt(rgbMatch[1], 16), parseInt(rgbMatch[2], 16), parseInt(rgbMatch[3], 16)]
            : [124, 58, 237];

          // Outer soft glow
          const grad = ctx.createRadialGradient(sx, sy, 0, sx, sy, radius * 1.4);
          grad.addColorStop(0,   `rgba(${rr},${gg},${bb},${alpha * 0.3})`);
          grad.addColorStop(0.5, `rgba(${rr},${gg},${bb},${alpha * 0.15})`);
          grad.addColorStop(1,   `rgba(${rr},${gg},${bb},0)`);
          ctx.beginPath();
          ctx.arc(sx, sy, radius * 1.4, 0, Math.PI * 2);
          ctx.fillStyle = grad;
          ctx.fill();

          // Sharp ring edge
          ctx.beginPath();
          ctx.arc(sx, sy, radius, 0, Math.PI * 2);
          ctx.strokeStyle = `rgba(${rr},${gg},${bb},${alpha})`;
          ctx.lineWidth   = 2.5 * dpr;
          ctx.stroke();
        }
      }

      if (animationsRef.current.length > 0) {
        rafRef.current = requestAnimationFrame(tick);
      } else {
        // All done — clear residual pixels and stop loop
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        rafRef.current = null;
      }
    };

    drawLoopRef.current = tick;
    rafRef.current      = requestAnimationFrame(tick);
  }, []);

  // Enqueue an animation and ensure the draw loop is running
  const triggerAnimation = useCallback(
    (nodeId, type, color) => {
      animationsRef.current.push({ nodeId, type, color, startTime: performance.now() });
      startDrawLoop();
    },
    [startDrawLoop],
  );

  // Stable ref for triggerAnimation (so mount-effect event handlers stay current)
  const triggerAnimationRef = useRef(triggerAnimation);
  useEffect(() => { triggerAnimationRef.current = triggerAnimation; }, [triggerAnimation]);

  // ── Layout control ─────────────────────────────────────────────────────────
  const stopLayout = useCallback(() => {
    if (layoutRef.current) {
      layoutRef.current.stop();
      layoutRef.current = null;
    }
    if (layoutTimeoutRef.current) {
      clearTimeout(layoutTimeoutRef.current);
      layoutTimeoutRef.current = null;
    }
    onLayoutChangeRef.current?.(false);
  }, []);

  const runLayout = useCallback(
    (g) => {
      if (!g || g.order === 0) return;
      stopLayout();
      try {
        const inferredSettings = forceAtlas2.inferSettings(g);
        const layout = new FA2Layout(g, {
          settings: {
            ...inferredSettings,
            gravity: 0.3,
            scalingRatio: 30,
            slowDown: 2,
            strongGravityMode: false,
            barnesHutOptimize: g.order > 300,
            barnesHutTheta: 0.6,
            adjustSizes: true,
            linLogMode: false,
            outboundAttractionDistribution: true,
          },
        });
        layoutRef.current = layout;
        layout.start();
        onLayoutChangeRef.current?.(true);
        const duration = getLayoutDuration(g.order);
        layoutTimeoutRef.current = setTimeout(() => {
          if (layoutRef.current) {
            layoutRef.current.stop();
            layoutRef.current = null;
            noverlap.assign(g, NOVERLAP_SETTINGS);
            sigmaRef.current?.refresh();
            onLayoutChangeRef.current?.(false);
          }
        }, duration);
      } catch (err) {
        console.warn('[GraphExplorer] FA2 worker unavailable:', err);
        onLayoutChangeRef.current?.(false);
      }
    },
    [stopLayout],
  );

  // ── Mount effect — Sigma initialized ONCE ─────────────────────────────────
  useEffect(() => {
    if (!containerRef.current || !overlayRef.current) return;

    const sigma  = new Sigma(new MultiGraph(), containerRef.current, {
      ...SIGMA_SETTINGS,
      nodeReducer: (node, data) => {
        const g   = graphRef.current;
        const res = { ...data };

        // Node type visibility
        if (activeTypesRef.current && !activeTypesRef.current.has(data.group)) {
          res.hidden = true;
          return res;
        }

        // Phase 4: Depth (BFS hop) filter — hide nodes beyond N hops from selection
        if (bfsReachableRef.current && !bfsReachableRef.current.has(node)) {
          res.hidden = true;
          return res;
        }

        const activeNode = selectedNodeRef.current;
        if (activeNode && g) {
          const isTarget   = node === activeNode;
          const isNeighbor = g.hasEdge(node, activeNode) || g.hasEdge(activeNode, node);
          if (isTarget) {
            res.color = data.color; res.size = (data.size || 8) * 1.8; res.zIndex = 2; res.highlighted = true;
          } else if (isNeighbor) {
            res.color = data.color; res.size = (data.size || 8) * 1.3; res.zIndex = 1;
          } else {
            res.color = dimColor(data.color, 0.25); res.size = (data.size || 8) * 0.6; res.zIndex = 0;
          }
        }
        return res;
      },
      edgeReducer: (edge, data) => {
        const g = graphRef.current;
        if (!g) return { ...data };
        const res = { ...data };

        // Node-type filter: hide edge if either endpoint type is off
        if (activeTypesRef.current) {
          const srcGroup = g.getNodeAttribute(g.source(edge), 'group');
          const tgtGroup = g.getNodeAttribute(g.target(edge), 'group');
          if (!activeTypesRef.current.has(srcGroup) || !activeTypesRef.current.has(tgtGroup)) {
            res.hidden = true;
            return res;
          }
        }

        // Phase 4: Edge type (label) filter
        if (activeEdgeTypesRef.current && activeEdgeTypesRef.current.size > 0) {
          const edgeLabel = data.label || '';
          if (!activeEdgeTypesRef.current.has(edgeLabel)) {
            res.hidden = true;
            return res;
          }
        }

        // Phase 4: Depth filter — hide edge if either endpoint is outside BFS set
        if (bfsReachableRef.current) {
          const src = g.source(edge);
          const tgt = g.target(edge);
          if (!bfsReachableRef.current.has(src) || !bfsReachableRef.current.has(tgt)) {
            res.hidden = true;
            return res;
          }
        }

        const activeNode = selectedNodeRef.current;
        if (activeNode) {
          const isConnected = g.source(edge) === activeNode || g.target(edge) === activeNode;
          if (isConnected) {
            res.color = brightenColor(data.color || '#94A3B8', 1.5);
            res.size  = Math.max(3, (data.size || 1) * 3.5);
            res.zIndex = 2;
          } else {
            res.color = dimColor(data.color || '#94A3B8', 0.1);
            res.size  = 0.3;
            res.zIndex = 0;
          }
        }
        return res;
      },
    });

    sigmaRef.current = sigma;

    // ── Overlay canvas: sync size with container using ResizeObserver ──────
    const canvas    = overlayRef.current;
    const container = containerRef.current;

    const syncCanvasSize = () => {
      const { width, height } = container.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      canvas.width  = width  * dpr;
      canvas.height = height * dpr;
      canvas.style.width  = `${width}px`;
      canvas.style.height = `${height}px`;
    };
    syncCanvasSize();
    const ro = new ResizeObserver(syncCanvasSize);
    ro.observe(container);

    // LOD camera handler
    const handleCameraUpdate = () => {
      const g = graphRef.current;
      if (!g) return;
      const ratio = sigma.getCamera().ratio;
      g.forEachNode((nodeId, attrs) => {
        if (ratio > 2.5)      g.setNodeAttribute(nodeId, 'label', attrs.size >= 18 ? attrs._label : '');
        else if (ratio > 0.8) g.setNodeAttribute(nodeId, 'label', attrs.size >= 10 ? attrs._label : '');
        else                  g.setNodeAttribute(nodeId, 'label', attrs._label);
      });
      sigma.refresh();
    };
    sigma.getCamera().on('updated', handleCameraUpdate);

    // ── Sigma event handlers ───────────────────────────────────────────────
    sigma.on('enterNode', ({ node }) => {
      hoveredNodeRef.current = node;
      if (containerRef.current) containerRef.current.style.cursor = 'pointer';
      const g = graphRef.current;
      if (g && g.hasNode(node)) {
        const attrs = g.getNodeAttributes(node);
        onNodeHoverRef.current?.(node, attrs.label || node, attrs.group || 'Entity', attrs.color);
      }
      if (!selectedNodeRef.current) sigma.refresh();
    });

    sigma.on('leaveNode', () => {
      hoveredNodeRef.current = null;
      if (containerRef.current) containerRef.current.style.cursor = 'grab';
      onNodeHoverRef.current?.(null, null, null, null);
      if (!selectedNodeRef.current) sigma.refresh();
    });

    sigma.on('clickNode', ({ node }) => {
      selectedNodeRef.current = node;
      bfsReachableRef.current = bfsReachable(graphRef.current, node, depthFilterRef.current);
      const g     = graphRef.current;
      const attrs = g && g.hasNode(node) ? g.getNodeAttributes(node) : {};
      const pos   = sigma.getNodeDisplayData(node);
      if (pos) sigma.getCamera().animate({ x: pos.x, y: pos.y, ratio: 0.15 }, { duration: 400 });
      const cam = sigma.getCamera();
      cam.animate({ ratio: cam.ratio * 1.0001 }, { duration: 50 });
      onNodeSelectRef.current?.(node, attrs.label || node, attrs.group || 'Entity', attrs.color);
      // Phase 3: purple click glow animation
      triggerAnimationRef.current(node, 'click', attrs.color || '#7c3aed');
      sigma.refresh();
    });

    sigma.on('clickStage', () => {
      selectedNodeRef.current = null;
      onNodeSelectRef.current?.(null, null, null, null);
      sigma.refresh();
    });

    return () => {
      if (rafRef.current) { cancelAnimationFrame(rafRef.current); rafRef.current = null; }
      ro.disconnect();
      stopLayout();
      sigma.kill();
      sigmaRef.current    = null;
      graphRef.current    = null;
      hoveredNodeRef.current  = null;
      selectedNodeRef.current = null;
    };
  }, []); // runs ONCE

  // ── Graph-swap effect ──────────────────────────────────────────────────────
  useEffect(() => {
    const sigma = sigmaRef.current;
    if (!sigma || !graph) return;
    stopLayout();
    graphRef.current = graph;
    sigma.setGraph(graph);
    graph.forEachNode((nodeId, attrs) => {
      graph.setNodeAttribute(nodeId, '_label', attrs.label);
    });
    sigma.getCamera().emit('updated');
    const counts = {};
    graph.forEachNode((id, attrs) => { counts[attrs.group] = (counts[attrs.group] || 0) + 1; });
    onTypeCounts?.(counts);
    onGraphReady?.(graph);
    selectedNodeRef.current = null;
    onNodeSelectRef.current?.(null, null, null, null);
    // Clear any in-flight animations from the old graph
    animationsRef.current = [];
    setTimeout(() => { sigmaRef.current?.getCamera().animatedReset({ duration: 500 }); }, 100);
  }, [graph, stopLayout]);

  // ── Search effect ──────────────────────────────────────────────────────────
  useEffect(() => {
    if (!search || !sigmaRef.current || !graphRef.current) return;
    const g    = graphRef.current;
    const term = search.toLowerCase();
    let found  = null;
    g.forEachNode((node) => {
      if (!found && node.toLowerCase().includes(term)) found = node;
    });
    if (found) {
      selectedNodeRef.current = found;
      bfsReachableRef.current = bfsReachable(g, found, depthFilterRef.current);
      const attrs = g.getNodeAttributes(found);
      const pos   = sigmaRef.current.getNodeDisplayData(found);
      if (pos) sigmaRef.current.getCamera().animate({ x: pos.x, y: pos.y, ratio: 0.15 }, { duration: 500 });
      onNodeSelectRef.current?.(found, attrs.label || found, attrs.group || 'Entity', attrs.color);
      // Phase 3: cyan search pulse animation
      triggerAnimationRef.current(found, 'search', '#22D3EE');
      sigmaRef.current.refresh();
    }
  }, [search]);

  // ── activeTypes sync ───────────────────────────────────────────────────────
  useEffect(() => {
    activeTypesRef.current = activeTypes;
    if (sigmaRef.current) sigmaRef.current.refresh();
  }, [activeTypes]);

  // ── Phase 4: depthFilter + BFS cache sync ─────────────────────────────────
  useEffect(() => {
    depthFilterRef.current = depthFilter ?? 4;
    // Recompute BFS when depth changes (selectedNode may already be set)
    bfsReachableRef.current = bfsReachable(
      graphRef.current,
      selectedNodeRef.current,
      depthFilterRef.current,
    );
    if (sigmaRef.current) sigmaRef.current.refresh();
  }, [depthFilter]);

  // ── Phase 4: activeEdgeTypes sync ─────────────────────────────────────────
  useEffect(() => {
    activeEdgeTypesRef.current = activeEdgeTypes;
    if (sigmaRef.current) sigmaRef.current.refresh();
  }, [activeEdgeTypes]);

  // ── Public API ─────────────────────────────────────────────────────────────
  useImperativeHandle(ref, () => ({
    zoomIn()  { sigmaRef.current?.getCamera().animatedZoom({ duration: 200 }); },
    zoomOut() { sigmaRef.current?.getCamera().animatedUnzoom({ duration: 200 }); },
    fitView() { sigmaRef.current?.getCamera().animatedReset({ duration: 300 }); },
    focusNode(nodeId) {
      if (!sigmaRef.current) return;
      const pos = sigmaRef.current.getNodeDisplayData(nodeId);
      if (pos) sigmaRef.current.getCamera().animate({ x: pos.x, y: pos.y, ratio: 0.15 }, { duration: 400 });
    },
    clearSelection() {
      selectedNodeRef.current  = null;
      bfsReachableRef.current  = null; // clear depth filter
      onNodeSelectRef.current?.(null, null, null, null);
      animationsRef.current = [];
      if (sigmaRef.current) {
        sigmaRef.current.getCamera().animatedReset({ duration: 300 });
        sigmaRef.current.refresh();
      }
    },
    startLayout() { if (graphRef.current) runLayout(graphRef.current); },
    stopLayout()  { stopLayout(); },
  }));

  return (
    // Wrapper keeps the sigma container and overlay canvas perfectly stacked
    <div className="relative w-full h-full cursor-grab active:cursor-grabbing">
      {/* Sigma mounts here */}
      <div ref={containerRef} className="absolute inset-0" />
      {/* Animation overlay — pointer-events:none so clicks pass through */}
      <canvas
        ref={overlayRef}
        className="absolute inset-0 pointer-events-none"
        style={{ mixBlendMode: 'screen' }}
      />
    </div>
  );
});

export default GraphExplorer;

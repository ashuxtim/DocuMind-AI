import React, { useCallback, useRef, useState, useEffect } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { GraphControls } from './GraphControls';
import { CanvasStarfield } from './CanvasStarfield';
import { LoadingSpinner } from '@/components/shared/LoadingSpinner';
import { useGraphData } from '@/hooks/useGraphData';
import { useGraphHighlight } from '@/hooks/useGraphHighlight';
import { paintNode, paintLinkLabel } from '@/utils/graphPainters';
import { getNodeColor, getLinkColor, getLinkDash } from '@/utils/graphColors';

export default function GraphExplorer() {
  const { data, loading, tier, refetch } = useGraphData({ limit: 2000 });
  const { handleNodeHover, paintStateRef, hoveredNodeRef } = useGraphHighlight(data);

  const graphRef = useRef();
  const [searchTerm, setSearchTerm] = useState('');
  const [searchError, setSearchError] = useState(false);
  // Minimal state — only for UI that truly needs re-render
  const [hoveredNodeDisplay, setHoveredNodeDisplay] = useState(null);

  // --- Explosion effect (only for small graphs) ---
  const hasExplodedRef = useRef(false);
  useEffect(() => {
    if (!loading && data.nodes.length > 0 && !hasExplodedRef.current && graphRef.current && tier) {
      if (!tier.explosionEnabled) {
        // Skip explosion, just fit view
        setTimeout(() => {
          graphRef.current?.zoomToFit(1000, 80);
        }, 300);
        hasExplodedRef.current = true;
        return;
      }

      setTimeout(() => {
        data.nodes.forEach((node) => {
          const angle = Math.random() * Math.PI * 2;
          const distance = 100 + Math.random() * 300;
          const forceStrength = 20 + Math.random() * 30;
          node.vx = Math.cos(angle) * forceStrength;
          node.vy = Math.sin(angle) * forceStrength;
          node.fx = Math.cos(angle) * distance;
          node.fy = Math.sin(angle) * distance;
        });

        setTimeout(() => {
          data.nodes.forEach((node) => {
            node.fx = undefined;
            node.fy = undefined;
          });
        }, 1500);

        setTimeout(() => {
          graphRef.current?.zoomToFit(2000, 100);
        }, 2000);

        hasExplodedRef.current = true;
      }, 100);
    }
  }, [loading, data.nodes, tier]);

  // --- Freeze simulation after cooldown ---
  const onEngineStop = useCallback(() => {
    // Simulation settled — no need to keep ticking
    // graphRef.current?.pauseAnimation(); // Uncomment to fully freeze
  }, []);

  // --- Hover wrapper: update ref + minimal display state ---
  const onNodeHover = useCallback(
    (node) => {
      handleNodeHover(node);
      setHoveredNodeDisplay(node ? { id: node.id, group: node.group, connections: node.connections } : null);
    },
    [handleNodeHover]
  );

  // --- Viewport computation for culling ---
  const getViewport = useCallback(() => {
    const fg = graphRef.current;
    if (!fg) return null;
    const canvas = fg.canvas?.();
    if (!canvas) return null;
    const w = canvas.width;
    const h = canvas.height;
    // Convert screen corners to graph coordinates
    const topLeft = fg.screen2GraphCoords(0, 0);
    const bottomRight = fg.screen2GraphCoords(w, h);
    return {
      left: topLeft.x,
      top: topLeft.y,
      right: bottomRight.x,
      bottom: bottomRight.y,
    };
  }, []);

  // --- Stable paint callback (empty deps — reads from refs) ---
  const nodePainter = useCallback(
    (node, ctx, globalScale) => {
      paintStateRef.current.tier = tier || { showLabelsAtScale: 1.5, ambientGlow: true, labelDegreeThreshold: 0 };
      paintStateRef.current.viewport = getViewport();
      paintNode(node, ctx, globalScale, paintStateRef.current);
    },
    [tier, paintStateRef, getViewport]
  );

  // --- Link label painter ---
  const linkPainter = useCallback(
    (link, ctx, globalScale) => {
      if (tier) paintLinkLabel(link, ctx, globalScale, tier);
    },
    [tier]
  );

  // --- Link color (reads from highlight ref) ---
  const linkColorFn = useCallback(
    (link) => getLinkColor(link, paintStateRef.current.hoveredId, paintStateRef.current.highlightLinks),
    [paintStateRef]
  );

  const linkWidthFn = useCallback(
    (link) => (paintStateRef.current.highlightLinks.has(link) ? 2.8 : 1.0),
    [paintStateRef]
  );

  const linkDashFn = useCallback((link) => getLinkDash(link), []);

  const linkParticlesFn = useCallback(
    (link) => {
      if (!tier?.showParticlesOnHover) return 0;
      return paintStateRef.current.highlightLinks.has(link) ? tier.particleCount : 0;
    },
    [tier, paintStateRef]
  );

  // --- Controls ---
  const handleZoomIn = useCallback(() => {
    graphRef.current?.zoom(graphRef.current.zoom() * 1.4, 400);
  }, []);

  const handleZoomOut = useCallback(() => {
    graphRef.current?.zoom(graphRef.current.zoom() / 1.4, 400);
  }, []);

  const handleFitView = useCallback(() => {
    graphRef.current?.zoomToFit(400, 80);
  }, []);

  const handleReset = useCallback(() => {
    hasExplodedRef.current = false;
    refetch();
    setSearchTerm('');
    setSearchError(false);
    setHoveredNodeDisplay(null);
  }, [refetch]);

  const handleSearch = useCallback(() => {
    const term = searchTerm.trim().toLowerCase();
    if (!term) return;

    const node = data.nodes.find((n) => n.id && n.id.toLowerCase().includes(term));
    if (node && graphRef.current) {
      setSearchError(false);
      graphRef.current.centerAt(node.x, node.y, 1000);
      graphRef.current.zoom(8, 2000);
      onNodeHover(node);
    } else {
      setSearchError(true);
      setTimeout(() => setSearchError(false), 2000);
    }
  }, [searchTerm, data.nodes, onNodeHover]);

  // --- Tooltip ---
  const getNodeTooltip = useCallback((node) => {
    if (!node) return null;
    const color = getNodeColor(node, null, new Set());
    return `
      <div style="
        background: linear-gradient(135deg, #1F2937 0%, #111827 100%);
        border: 1px solid rgba(99, 102, 241, 0.4);
        border-radius: 8px;
        padding: 12px 16px;
        color: #F9FAFB;
        font-family: Inter, system-ui, sans-serif;
        box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.7);
        min-width: 200px;
      ">
        <div style="font-size: 14px; font-weight: 600; margin-bottom: 8px; color: ${color};">
          ${node.id}
        </div>
        <div style="display: flex; gap: 16px; font-size: 12px; color: #9CA3AF;">
          <div>
            <span style="color: #6B7280;">Type:</span>
            <strong style="color: #D1D5DB; margin-left: 4px;">${node.group}</strong>
          </div>
          <div>
            <span style="color: #6B7280;">Links:</span>
            <strong style="color: #D1D5DB; margin-left: 4px;">${node.connections}</strong>
          </div>
        </div>
      </div>
    `;
  }, []);

  if (loading || !tier) {
    return (
      <div className="flex items-center justify-center h-full bg-black">
        <LoadingSpinner size="lg" text="Loading knowledge graph..." />
      </div>
    );
  }

  return (
    <div className="relative w-full h-full bg-black overflow-hidden">
      {/* Canvas Starfield */}
      <CanvasStarfield />

      <GraphControls
        onZoomIn={handleZoomIn}
        onZoomOut={handleZoomOut}
        onFitView={handleFitView}
        onReset={handleReset}
        searchTerm={searchTerm}
        onSearchChange={setSearchTerm}
        onSearch={handleSearch}
        searchError={searchError}
        nodeCount={data.nodes.length}
        linkCount={data.links.length}
      />

      <div className="w-full h-full" style={{ opacity: 1 }}>
        <ForceGraph2D
          ref={graphRef}
          graphData={data}
          nodeLabel={getNodeTooltip}
          nodeCanvasObject={nodePainter}
          nodePointerAreaPaint={(node, color, ctx) => {
            const r = Math.max(3, Math.sqrt(node.val || 1) * 4);
            ctx.fillStyle = color;
            ctx.beginPath();
            ctx.arc(node.x, node.y, r + 2, 0, 2 * Math.PI);
            ctx.fill();
          }}
          linkColor={linkColorFn}
          linkWidth={linkWidthFn}
          linkLineDash={linkDashFn}
          linkCurvature={0.12}
          linkDirectionalArrowLength={5}
          linkDirectionalArrowRelPos={1}
          linkDirectionalParticles={linkParticlesFn}
          linkDirectionalParticleWidth={2.5}
          linkDirectionalParticleSpeed={0.004}
          linkDirectionalParticleColor={() => 'rgba(99, 102, 241, 0.8)'}
          linkCanvasObjectMode="after"
          linkCanvasObject={linkPainter}
          backgroundColor="rgba(0,0,0,0)"
          onNodeHover={onNodeHover}
          onNodeClick={(node) => {
            if (graphRef.current) {
              graphRef.current.centerAt(node.x, node.y, 1000);
              graphRef.current.zoom(6, 1000);
            }
          }}
          onEngineStop={onEngineStop}
          enableNodeDrag={true}
          enableZoomInteraction={true}
          enablePanInteraction={true}
          d3AlphaDecay={0.015}
          d3AlphaMin={0.01}
          d3VelocityDecay={tier.d3VelocityDecay}
          warmupTicks={tier.warmupTicks}
          cooldownTicks={tier.cooldownTicks}
          cooldownTime={10000}
        />
      </div>

      {/* Hover Info Panel — only re-renders when hoveredNodeDisplay changes */}
      {hoveredNodeDisplay && (
        <div className="absolute bottom-6 left-6 bg-slate-900/95 backdrop-blur-sm border border-indigo-500/30 rounded-lg p-4 shadow-2xl animate-in fade-in slide-in-from-bottom-2 duration-200">
          <h4 className="text-sm font-semibold text-emerald-400 mb-2">
            {hoveredNodeDisplay.id}
          </h4>
          <div className="flex gap-4 text-xs text-slate-400">
            <div>
              <span className="text-slate-500">Type:</span>
              <span className="ml-2 text-slate-200">{hoveredNodeDisplay.group}</span>
            </div>
            <div>
              <span className="text-slate-500">Connections:</span>
              <span className="ml-2 text-slate-200">{hoveredNodeDisplay.connections}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

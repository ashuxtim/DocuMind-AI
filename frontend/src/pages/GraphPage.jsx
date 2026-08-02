import { useState, useRef, useCallback } from 'react';
import { Network, RefreshCw, Filter, BarChart2, X, GitBranch, Target } from 'lucide-react';
import { useGraphData } from '@/hooks/useGraphData';
import GraphExplorer from '@/components/graph/GraphExplorer';
import { GraphFilterPanel } from '@/components/graph/GraphFilterPanel';
import { GraphStatsPanel } from '@/components/graph/GraphStatsPanel';
import { GraphControlsWidget } from '@/components/graph/GraphControlsWidget';
import { GraphSearchPalette } from '@/components/graph/GraphSearchPalette';
import { Button } from '@/ui/button';
import { Badge } from '@/ui/badge';

const ALL_TYPES = ['Person', 'Organization', 'Statute', 'Date', 'Document', 'Entity'];

const NODE_COLORS = [
  { label: 'Person',       color: '#34D399' },
  { label: 'Organization', color: '#FBBF24' },
  { label: 'Statute',      color: '#A78BFA' },
  { label: 'Date',         color: '#22D3EE' },
  { label: 'Document',     color: '#F472B6' },
  { label: 'Entity',       color: '#94A3B8' },
];

const TYPE_COLORS = {
  Person: '#34D399', Organization: '#FBBF24', Statute: '#A78BFA',
  Date: '#22D3EE',  Document: '#F472B6',     Entity: '#94A3B8',
};

// View mode definitions — only Force is fully implemented;
// Tree and Circles are shown as "coming soon" (disabled).
const VIEW_MODES = [
  { id: 'force',   label: 'Force',   icon: Network,   enabled: true  },
  { id: 'tree',    label: 'Tree',    icon: GitBranch, enabled: false },
  { id: 'circles', label: 'Circles', icon: Target,    enabled: false },
];

export function GraphPage() {
  const { graph, loading, error, refetch, nodeCount, linkCount } = useGraphData();

  const [committedSearch, setCommittedSearch] = useState('');
  const [filterOpen,  setFilterOpen]  = useState(false);
  const [statsOpen,   setStatsOpen]   = useState(false);
  const [activeTypes, setActiveTypes] = useState(new Set(ALL_TYPES));
  const [typeCounts,  setTypeCounts]  = useState({});
  const [liveGraph,   setLiveGraph]   = useState(null);

  // ── Phase 1: selection + hover state ─────────────────────────────────────────
  const [selectedNode, setSelectedNode] = useState(null);  // { id, label, group, color }
  const [hoveredNode,  setHoveredNode]  = useState(null);  // { id, label, group, color }

  // ── Phase 2: layout + view mode state ────────────────────────────────────────
  const [isLayoutRunning, setIsLayoutRunning] = useState(false);
  const [graphViewMode,   setGraphViewMode]   = useState('force');

  // ── Phase 4: filter & depth state ────────────────────────────────────────────
  const [depthFilter,     setDepthFilter]     = useState(4);
  const [edgeTypes,       setEdgeTypes]       = useState([]);
  const [activeEdgeTypes, setActiveEdgeTypes] = useState(new Set());

  const explorerRef = useRef(null);

  // ── Callbacks ─────────────────────────────────────────────────────────────────

  const handleSelectNodeFromSearch = useCallback((nodeId) => {
    setCommittedSearch(nodeId);
  }, []);

  const handleNodeSelect = useCallback((id, label, group, color) => {
    setSelectedNode(id ? { id, label, group, color } : null);
  }, []);

  const handleNodeHover = useCallback((id, label, group, color) => {
    setHoveredNode(id ? { id, label, group, color } : null);
  }, []);

  const handleClearSelection = useCallback(() => {
    explorerRef.current?.clearSelection();
    setSelectedNode(null);
  }, []);

  const handleFocusSelected = useCallback(() => {
    if (selectedNode) explorerRef.current?.focusNode(selectedNode.id);
  }, [selectedNode]);

  // Called by GraphExplorer whenever layout starts/stops
  const handleLayoutChange = useCallback((running) => {
    setIsLayoutRunning(running);
  }, []);

  // Play/Pause toggle from the controls widget
  const handleToggleLayout = useCallback(() => {
    if (isLayoutRunning) {
      explorerRef.current?.stopLayout();
    } else {
      explorerRef.current?.startLayout();
    }
  }, [isLayoutRunning]);

  // View mode tab click — only 'force' is active; others show tooltip
  const handleViewModeChange = useCallback((modeId) => {
    if (modeId === graphViewMode) return;
    setGraphViewMode(modeId);
    // Future: trigger different graph adapter here (tree / circles layout)
  }, [graphViewMode]);

  const handleToggleType = useCallback((type) => {
    setActiveTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) {
        if (next.size === 1) return prev;
        next.delete(type);
      } else {
        next.add(type);
      }
      return next;
    });
  }, []);

  const handleShowAll = useCallback(() => setActiveTypes(new Set(ALL_TYPES)), []);

  const handleHideAll = useCallback(() => {
    const mostConnected =
      Object.entries(typeCounts).sort(([, a], [, b]) => b - a)[0]?.[0] ?? 'Entity';
    setActiveTypes(new Set([mostConnected]));
  }, [typeCounts]);

  const handleGraphReady = useCallback((g) => {
    setLiveGraph(g);
    // Extract unique edge types
    const eTypes = new Set();
    g.forEachEdge((edge, attrs) => {
      if (attrs.label) eTypes.add(attrs.label);
    });
    const sortedETypes = Array.from(eTypes).sort();
    setEdgeTypes(sortedETypes);
    setActiveEdgeTypes(new Set(sortedETypes));
  }, []);

  const handleToggleEdgeType = useCallback((type) => {
    setActiveEdgeTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) {
        if (next.size === 1) return prev;
        next.delete(type);
      } else {
        next.add(type);
      }
      return next;
    });
  }, []);

  const handleShowAllEdges = useCallback(() => setActiveEdgeTypes(new Set(edgeTypes)), [edgeTypes]);
  const handleHideAllEdges = useCallback(() => setActiveEdgeTypes(new Set()), []);

  const hiddenCount       = ALL_TYPES.length - activeTypes.size;
  const showHoverTooltip  = hoveredNode && !selectedNode;

  return (
    <div className="relative w-full h-full overflow-hidden bg-[#06060a]">

      {/* ── Background gradient (Phase 1) ── */}
      <div className="pointer-events-none absolute inset-0 z-0">
        <div
          className="absolute inset-0"
          style={{
            background: `
              radial-gradient(circle at 50% 50%, rgba(124, 58, 237, 0.04) 0%, transparent 65%),
              linear-gradient(to bottom, #06060a, #0a0a10)
            `,
          }}
        />
      </div>

      {/* ── Floating Header Navigation Bar ── */}
      <div className="absolute top-3 left-3 right-3 z-20 flex items-center justify-between gap-3 px-4 py-2.5 rounded-xl bg-[#101018]/85 backdrop-blur-md border border-[#2a2a3a] shadow-glass flex-wrap">
        {/* Brand & Title */}
        <div className="flex items-center gap-3 min-w-0">
          <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-[#7c3aed]/20 border border-[#7c3aed]/40">
            <Network className="w-4 h-4 text-[#7c3aed]" />
          </div>
          <div>
            <h1 className="text-sm font-semibold text-[#e4e4ed] leading-tight font-sans tracking-wide">
              Knowledge Graph
            </h1>
            <p className="text-[11px] text-[#8888a0] leading-tight font-sans">
              DocuMind Entity Network
            </p>
          </div>
        </div>

        {/* Node Types Color Legend */}
        <div className="hidden lg:flex items-center gap-3 px-3 py-1.5 rounded-lg bg-[#0a0a10]/60 border border-[#1e1e2a]">
          {NODE_COLORS.map(({ label, color }) => (
            <span key={label} className="flex items-center gap-1.5 text-xs text-[#8888a0] font-sans">
              <span
                className="inline-block w-2 h-2 rounded-full flex-none"
                style={{ backgroundColor: color }}
              />
              {label}
            </span>
          ))}
        </div>

        {/* Stats & Controls */}
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="bg-[#0a0a10]/80 border-[#2a2a3a] text-[#e4e4ed] text-xs font-mono tabular-nums">
            {nodeCount.toLocaleString()} <span className="text-[#8888a0] ml-1">nodes</span>
          </Badge>
          <Badge variant="outline" className="bg-[#0a0a10]/80 border-[#2a2a3a] text-[#e4e4ed] text-xs font-mono tabular-nums">
            {linkCount.toLocaleString()} <span className="text-[#8888a0] ml-1">edges</span>
          </Badge>

          <GraphSearchPalette graph={liveGraph} onSelectNode={handleSelectNodeFromSearch} />

          {/* Filter toggle */}
          <div className="relative">
            <Button
              variant={filterOpen ? 'default' : 'outline'}
              size="icon"
              className={`h-8 w-8 rounded-lg border-2 font-medium transition-all ${
                filterOpen
                  ? 'bg-[#7c3aed] text-white border-[#7c3aed] shadow-[0_0_12px_rgba(124,58,237,0.4)]'
                  : 'bg-[#0a0a10]/80 border-[#2a2a3a] text-[#e4e4ed] hover:bg-[#1c1c28] hover:border-[#7c3aed]/50'
              }`}
              title="Filter by entity type"
              onClick={() => setFilterOpen((o) => !o)}
            >
              <Filter className="w-3.5 h-3.5" />
            </Button>
            {hiddenCount > 0 && (
              <span className="absolute -top-1 -right-1 flex items-center justify-center w-4 h-4 rounded-full bg-[#ef4444] text-[10px] font-bold text-white leading-none shadow-md">
                {hiddenCount}
              </span>
            )}
          </div>

          {/* Stats toggle */}
          <Button
            variant={statsOpen ? 'default' : 'outline'}
            size="icon"
            className={`h-8 w-8 rounded-lg border transition-all ${
              statsOpen
                ? 'bg-[#7c3aed] text-white border-[#7c3aed] shadow-[0_0_12px_rgba(124,58,237,0.4)]'
                : 'bg-[#0a0a10]/80 border-[#2a2a3a] text-[#e4e4ed] hover:bg-[#1c1c28] hover:border-[#7c3aed]/50'
            }`}
            title="Graph statistics"
            onClick={() => setStatsOpen((o) => !o)}
          >
            <BarChart2 className="w-3.5 h-3.5" />
          </Button>

          {/* Refetch */}
          <Button
            variant="outline"
            size="icon"
            className="h-8 w-8 rounded-lg bg-[#0a0a10]/80 border-[#2a2a3a] text-[#e4e4ed] hover:bg-[#1c1c28] hover:border-[#7c3aed]/50 transition-all"
            title="Reload graph"
            onClick={refetch}
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </Button>
        </div>
      </div>

      {/* ── View Mode Tabs (top-center, below floating header) ── */}
      {graph && !loading && !error && (
        <div
          role="tablist"
          aria-label="Graph layout mode"
          className="absolute z-10 flex gap-1 rounded-lg border border-[#1e1e2a] bg-[#16161f]/90 p-1 backdrop-blur-sm"
          style={{ top: 72, left: '50%', transform: 'translateX(-50%)' }}
        >
          {VIEW_MODES.map(({ id, label, icon: Icon, enabled }) => (
            <button
              key={id}
              role="tab"
              aria-selected={graphViewMode === id}
              disabled={!enabled}
              onClick={() => enabled && handleViewModeChange(id)}
              title={enabled ? label : `${label} — coming soon`}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all ${
                graphViewMode === id && enabled
                  ? 'bg-[#7c3aed] text-white shadow-sm'
                  : enabled
                  ? 'text-[#8888a0] hover:bg-[#1c1c28] hover:text-[#e4e4ed]'
                  : 'text-[#3a3a50] cursor-not-allowed opacity-50'
              }`}
            >
              <Icon className="h-3.5 w-3.5" />
              {label}
              {!enabled && (
                <span className="ml-1 text-[9px] text-[#3a3a50] font-mono">soon</span>
              )}
            </button>
          ))}
        </div>
      )}

      {/* ── Hover tooltip (Phase 1 — sits above view mode tabs via z-20) ── */}
      {showHoverTooltip && (
        <div
          className="pointer-events-none absolute z-20 animate-fade-in"
          style={{ top: 72, left: '50%', transform: 'translateX(-50%)' }}
        >
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-[#2a2a3a] bg-[#16161f]/95 backdrop-blur-sm shadow-lg">
            <span
              className="w-2 h-2 rounded-full flex-none"
              style={{
                backgroundColor: hoveredNode.color || TYPE_COLORS[hoveredNode.group] || '#94A3B8',
                boxShadow: `0 0 6px ${hoveredNode.color || '#7c3aed'}`,
              }}
            />
            <span className="font-mono text-sm text-[#e4e4ed]">{hoveredNode.label}</span>
            <span className="text-xs text-[#5a5a70]">({hoveredNode.group})</span>
          </div>
        </div>
      )}

      {/* ── Selection info bar (Phase 1 — sits above view mode tabs via z-20) ── */}
      {selectedNode && (
        <div
          className="absolute z-20 flex items-center gap-2.5 px-4 py-2 rounded-xl border border-[#7c3aed]/30 bg-[#7c3aed]/15 backdrop-blur-sm shadow-lg animate-slide-up"
          style={{ top: 72, left: '50%', transform: 'translateX(-50%)' }}
        >
          <div
            className="h-2 w-2 rounded-full animate-pulse flex-none"
            style={{
              backgroundColor: selectedNode.color || TYPE_COLORS[selectedNode.group] || '#7c3aed',
              boxShadow: `0 0 8px ${selectedNode.color || '#7c3aed'}`,
            }}
          />
          <span className="font-mono text-sm text-[#e4e4ed] max-w-[220px] truncate">
            {selectedNode.label}
          </span>
          <span
            className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded-full flex-none"
            style={{
              backgroundColor: `${selectedNode.color || TYPE_COLORS[selectedNode.group] || '#7c3aed'}22`,
              color:  selectedNode.color || TYPE_COLORS[selectedNode.group] || '#a78bfa',
              border: `1px solid ${selectedNode.color || TYPE_COLORS[selectedNode.group] || '#7c3aed'}44`,
            }}
          >
            {selectedNode.group}
          </span>
          <button
            onClick={handleClearSelection}
            className="ml-1 flex items-center justify-center w-5 h-5 rounded text-[#8888a0] hover:text-[#e4e4ed] hover:bg-white/10 transition-colors flex-none"
            title="Clear selection"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* ── Full-viewport Graph Canvas ── */}
      <div className="w-full h-full absolute inset-0">
        {loading && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 z-30 bg-[#06060a]/90 backdrop-blur-md">
            <div className="w-9 h-9 border-2 border-[#7c3aed] border-t-transparent rounded-full animate-spin shadow-[0_0_20px_rgba(124,58,237,0.4)]" />
            <p className="text-xs font-mono text-[#8888a0]">Initializing Knowledge Graph...</p>
          </div>
        )}

        {error && !loading && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 z-30 bg-[#06060a]/90 backdrop-blur-md">
            <p className="text-sm text-[#ef4444] font-medium">{error}</p>
            <Button variant="outline" size="sm" onClick={refetch} className="bg-[#101018] border-[#2a2a3a] text-[#e4e4ed] hover:bg-[#1c1c28]">
              <RefreshCw className="w-3.5 h-3.5 mr-2" />
              Retry Connection
            </Button>
          </div>
        )}

        <GraphFilterPanel
          isOpen={filterOpen}
          onClose={() => setFilterOpen(false)}
          activeTypes={activeTypes}
          onToggleType={handleToggleType}
          onShowAll={handleShowAll}
          onHideAll={handleHideAll}
          typeCounts={typeCounts}
          depthFilter={depthFilter}
          onDepthChange={setDepthFilter}
          selectedNodeLabel={selectedNode?.label}
          edgeTypes={edgeTypes}
          activeEdgeTypes={activeEdgeTypes}
          onToggleEdgeType={handleToggleEdgeType}
          onShowAllEdges={handleShowAllEdges}
          onHideAllEdges={handleHideAllEdges}
        />

        <GraphStatsPanel
          isOpen={statsOpen}
          onClose={() => setStatsOpen(false)}
          graph={liveGraph}
        />

        {graph && !loading && !error && (
          <div className="w-full h-full">
            <GraphExplorer
              ref={explorerRef}
              graph={graph}
              search={committedSearch}
              activeTypes={activeTypes}
              onTypeCounts={setTypeCounts}
              onGraphReady={handleGraphReady}
              onNodeSelect={handleNodeSelect}
              onNodeHover={handleNodeHover}
              onLayoutChange={handleLayoutChange}
              depthFilter={depthFilter}
              activeEdgeTypes={activeEdgeTypes}
            />
          </div>
        )}
      </div>

      {/* ── Camera Controls Widget (Phase 1 + Phase 2) ── */}
      {graph && !loading && !error && (
        <GraphControlsWidget
          onZoomIn={() => explorerRef.current?.zoomIn()}
          onZoomOut={() => explorerRef.current?.zoomOut()}
          onFitView={() => explorerRef.current?.fitView()}
          onFocusSelected={handleFocusSelected}
          onClearSelection={handleClearSelection}
          onToggleLayout={handleToggleLayout}
          selectedNode={selectedNode?.label ?? null}
          isLayoutRunning={isLayoutRunning}
        />
      )}

      {/* ── Bottom-center: layout indicator OR footer hint ── */}
      <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-20 pointer-events-none hidden sm:block">
        {isLayoutRunning ? (
          // Layout running indicator (emerald ping dot — GitNexus style)
          <div className="flex items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-500/15 px-3 py-1.5 backdrop-blur-sm animate-fade-in">
            <div className="h-2 w-2 animate-ping rounded-full bg-emerald-400 flex-none" />
            <span className="text-xs font-medium text-emerald-400 font-sans">
              Optimizing layout…
            </span>
          </div>
        ) : (
          // Static hint pill
          <div className="px-4 py-1.5 rounded-full bg-[#101018]/85 backdrop-blur-md border border-[#2a2a3a] shadow-lg">
            <p className="text-[11px] text-[#8888a0] font-mono text-center tracking-tight">
              Click to focus node · Search by name · Drag to pan · Scroll to zoom
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

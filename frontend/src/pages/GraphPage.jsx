import { useState, useRef, useCallback } from 'react';
import { Network, RefreshCw, Filter, BarChart2, Search } from 'lucide-react';
import { useGraphData } from '@/hooks/useGraphData';
import GraphExplorer from '@/components/graph/GraphExplorer';
import { GraphFilterPanel } from '@/components/graph/GraphFilterPanel';
import { GraphStatsPanel } from '@/components/graph/GraphStatsPanel';
import { GraphControlsWidget } from '@/components/graph/GraphControlsWidget';
import { Button } from '@/ui/button';
import { Input } from '@/ui/input';
import { Badge } from '@/ui/badge';

const ALL_TYPES = ['Person', 'Organization', 'Statute', 'Date', 'Document', 'Entity'];

const NODE_COLORS = [
  { label: 'Person', color: '#34D399' },
  { label: 'Organization', color: '#FBBF24' },
  { label: 'Statute', color: '#A78BFA' },
  { label: 'Date', color: '#22D3EE' },
  { label: 'Document', color: '#F472B6' },
  { label: 'Entity', color: '#94A3B8' },
];

export function GraphPage() {
  const { graph, loading, error, refetch, nodeCount, linkCount } = useGraphData();
  const [searchValue, setSearchValue] = useState('');
  const [committedSearch, setCommittedSearch] = useState('');
  const [filterOpen, setFilterOpen] = useState(false);
  const [statsOpen, setStatsOpen] = useState(false);
  const [activeTypes, setActiveTypes] = useState(new Set(ALL_TYPES));
  const [typeCounts, setTypeCounts] = useState({});
  const [liveGraph, setLiveGraph] = useState(null);
  const explorerRef = useRef(null);

  const handleSearchKeyDown = useCallback(
    (e) => {
      if (e.key === 'Enter') setCommittedSearch(searchValue);
    },
    [searchValue],
  );

  const handleToggleType = useCallback((type) => {
    setActiveTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) {
        if (next.size === 1) return prev; // never hide the last type
        next.delete(type);
      } else {
        next.add(type);
      }
      return next;
    });
  }, []);

  const handleShowAll = useCallback(() => {
    setActiveTypes(new Set(ALL_TYPES));
  }, []);

  const handleHideAll = useCallback(() => {
    const mostConnected =
      Object.entries(typeCounts).sort(([, a], [, b]) => b - a)[0]?.[0] ?? 'Entity';
    setActiveTypes(new Set([mostConnected]));
  }, [typeCounts]);

  const handleGraphReady = useCallback((g) => {
    setLiveGraph(g);
  }, []);

  const hiddenCount = ALL_TYPES.length - activeTypes.size;

  return (
    <div className="relative w-full h-full overflow-hidden bg-[#06060a]">
      {/* ── Floating Header Navigation Bar (GitNexus Style) ── */}
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

        {/* Node Types Color Legend Pill Bar */}
        <div className="hidden lg:flex items-center gap-3 px-3 py-1.5 rounded-lg bg-[#0a0a10]/60 border border-[#1e1e2a]">
          {NODE_COLORS.map(({ label, color }) => (
            <span key={label} className="flex items-center gap-1.5 text-xs text-[#8888a0] font-sans">
              <span
                className="inline-block w-2 h-2 rounded-full flex-none shadow-[0_0_8px_rgba(0,0,0,0.5)]"
                style={{ backgroundColor: color }}
              />
              {label}
            </span>
          ))}
        </div>

        {/* Controls & Metrics */}
        <div className="flex items-center gap-2">
          {/* Stats Badges */}
          <Badge variant="outline" className="bg-[#0a0a10]/80 border-[#2a2a3a] text-[#e4e4ed] text-xs font-mono tabular-nums">
            {nodeCount.toLocaleString()} <span className="text-[#8888a0] ml-1">nodes</span>
          </Badge>
          <Badge variant="outline" className="bg-[#0a0a10]/80 border-[#2a2a3a] text-[#e4e4ed] text-xs font-mono tabular-nums">
            {linkCount.toLocaleString()} <span className="text-[#8888a0] ml-1">edges</span>
          </Badge>

          {/* Search Input */}
          <div className="relative flex items-center">
            <Search className="w-3.5 h-3.5 absolute left-2.5 text-[#5a5a70] pointer-events-none" />
            <Input
              className="h-8 w-44 sm:w-56 text-xs pl-8 bg-[#0a0a10]/80 border-[#2a2a3a] text-[#e4e4ed] placeholder-[#5a5a70] focus:border-[#7c3aed] focus:ring-1 focus:ring-[#7c3aed] transition-all"
              placeholder="Search nodes (Enter)..."
              value={searchValue}
              onChange={(e) => setSearchValue(e.target.value)}
              onKeyDown={handleSearchKeyDown}
            />
          </div>

          {/* Filter Panel Toggle */}
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

          {/* Stats Panel Toggle */}
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

          {/* Refetch Button */}
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

      {/* ── 100% Full-Viewport Graph Canvas Container ── */}
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

        {/* Filter Panel (Slide-over) */}
        <GraphFilterPanel
          isOpen={filterOpen}
          onClose={() => setFilterOpen(false)}
          activeTypes={activeTypes}
          onToggleType={handleToggleType}
          onShowAll={handleShowAll}
          onHideAll={handleHideAll}
          typeCounts={typeCounts}
        />

        {/* Stats Panel (Slide-over) */}
        <GraphStatsPanel
          isOpen={statsOpen}
          onClose={() => setStatsOpen(false)}
          graph={liveGraph}
        />

        {/* Graph Explorer Canvas */}
        {graph && !loading && !error && (
          <div className="w-full h-full">
            <GraphExplorer
              ref={explorerRef}
              graph={graph}
              search={committedSearch}
              activeTypes={activeTypes}
              onTypeCounts={setTypeCounts}
              onGraphReady={handleGraphReady}
            />
          </div>
        )}
      </div>

      {/* ── Floating Camera Action Bar Widget (GitNexus Style) ── */}
      {graph && !loading && !error && (
        <GraphControlsWidget
          onZoomIn={() => explorerRef.current?.zoomIn()}
          onZoomOut={() => explorerRef.current?.zoomOut()}
          onFitView={() => explorerRef.current?.fitView()}
          onResetView={() => explorerRef.current?.fitView()}
        />
      )}

      {/* ── Floating Footer Hint Pill (GitNexus Style) ── */}
      <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-20 pointer-events-none hidden sm:block">
        <div className="px-4 py-1.5 rounded-full bg-[#101018]/85 backdrop-blur-md border border-[#2a2a3a] shadow-lg">
          <p className="text-[11px] text-[#8888a0] font-mono text-center tracking-tight">
            Click to focus node · Search by name · Drag to pan · Scroll to zoom
          </p>
        </div>
      </div>
    </div>
  );
}



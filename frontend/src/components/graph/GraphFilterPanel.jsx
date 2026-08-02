import { motion } from 'framer-motion';
import { X, Layers, Network } from 'lucide-react';

const ALL_TYPES = ['Person', 'Organization', 'Statute', 'Date', 'Document', 'Entity'];

const TYPE_COLORS = {
  Person:       '#34D399',
  Organization: '#FBBF24',
  Statute:      '#A78BFA',
  Date:         '#22D3EE',
  Document:     '#F472B6',
  Entity:       '#94A3B8',
};

// Depth labels shown beside the slider tick marks
const DEPTH_LABELS = { 1: '1 hop', 2: '2 hops', 3: '3 hops', 4: '4+ hops' };

export function GraphFilterPanel({
  isOpen,
  onClose,
  // Node type filter (existing)
  activeTypes,
  onToggleType,
  onShowAll,
  onHideAll,
  typeCounts,
  // Phase 4 — depth filter
  depthFilter,
  onDepthChange,
  selectedNodeLabel,
  // Phase 4 — edge type filter
  edgeTypes,
  activeEdgeTypes,
  onToggleEdgeType,
  onShowAllEdges,
  onHideAllEdges,
}) {
  const hasSelection     = !!selectedNodeLabel;
  const depthDisabled    = !hasSelection;
  const hasEdgeTypes     = edgeTypes && edgeTypes.length > 0;

  return (
    <motion.div
      initial={false}
      animate={{ x: isOpen ? 0 : -280 }}
      transition={{ type: 'spring', damping: 30, stiffness: 300 }}
      className="absolute top-16 left-3 bottom-14 z-20 flex flex-col"
      style={{ width: 256 }}
    >
      <div className="h-full flex flex-col bg-[#101018]/95 backdrop-blur-md border border-[#2a2a3a] rounded-xl shadow-glass overflow-hidden">

        {/* ── Header ── */}
        <div className="flex items-center justify-between px-3.5 py-3 border-b border-[#2a2a3a] flex-none">
          <span className="text-xs font-semibold text-[#e4e4ed] tracking-wider uppercase font-sans">
            Filters
          </span>
          <button
            onClick={onClose}
            className="flex items-center justify-center w-6 h-6 rounded-lg text-[#8888a0] hover:text-[#e4e4ed] hover:bg-[#1c1c28] transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* ── Scrollable body ── */}
        <div className="flex-1 overflow-y-auto scrollbar-thin">

          {/* ── Section: Node Types ── */}
          <div className="px-3.5 pt-3 pb-1">
            <div className="flex items-center gap-1.5 mb-2">
              <Network className="w-3 h-3 text-[#5a5a70]" />
              <span className="text-[10px] font-mono text-[#5a5a70] uppercase tracking-wider">
                Node Types
              </span>
            </div>
          </div>

          {ALL_TYPES.map((type) => {
            const active = activeTypes.has(type);
            const count  = typeCounts[type] ?? 0;
            return (
              <button
                key={type}
                onClick={() => onToggleType(type)}
                className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-left transition-all hover:bg-[#1c1c28]"
                style={{ opacity: active ? 1 : 0.4 }}
              >
                <span
                  className="flex-none w-2.5 h-2.5 rounded-full"
                  style={{ backgroundColor: TYPE_COLORS[type] }}
                />
                <span className="flex-1 text-xs text-[#e4e4ed] font-sans font-medium">
                  {type}
                </span>
                <span className="flex-none text-xs text-[#8888a0] font-mono tabular-nums">
                  {count.toLocaleString()}
                </span>
                <span
                  className="flex-none w-1.5 h-1.5 rounded-full transition-all"
                  style={{
                    backgroundColor: active ? TYPE_COLORS[type] : 'transparent',
                    boxShadow:       active ? `0 0 6px ${TYPE_COLORS[type]}` : 'none',
                  }}
                />
              </button>
            );
          })}

          {/* ── Section: Depth Filter ── */}
          <div className="px-3.5 pt-4 pb-3 border-t border-[#1e1e2a] mt-2">
            <div className="flex items-center gap-1.5 mb-3">
              <Layers className="w-3 h-3 text-[#5a5a70]" />
              <span className="text-[10px] font-mono text-[#5a5a70] uppercase tracking-wider">
                Depth Filter
              </span>
              {depthDisabled && (
                <span className="ml-auto text-[9px] font-mono text-[#3a3a50]">
                  select a node
                </span>
              )}
            </div>

            {/* Context hint */}
            {hasSelection && (
              <p className="text-[10px] font-mono text-[#5a5a70] mb-3 truncate">
                from: <span className="text-[#8888a0]">{selectedNodeLabel}</span>
              </p>
            )}

            {/* Slider */}
            <div className={`space-y-2 ${depthDisabled ? 'opacity-30 pointer-events-none' : ''}`}>
              <input
                type="range"
                min={1}
                max={4}
                step={1}
                value={depthFilter}
                onChange={(e) => onDepthChange(Number(e.target.value))}
                className="w-full accent-[#7c3aed] cursor-pointer"
                style={{ accentColor: '#7c3aed' }}
              />
              {/* Tick labels */}
              <div className="flex justify-between">
                {[1, 2, 3, 4].map((n) => (
                  <span
                    key={n}
                    className="text-[9px] font-mono transition-colors"
                    style={{ color: depthFilter === n ? '#7c3aed' : '#3a3a50' }}
                  >
                    {n === 4 ? '4+' : n}
                  </span>
                ))}
              </div>
              {/* Current value pill */}
              <div className="flex justify-center mt-1">
                <span className="text-[10px] font-mono text-[#7c3aed] bg-[#7c3aed]/10 border border-[#7c3aed]/30 px-2 py-0.5 rounded-full">
                  {DEPTH_LABELS[depthFilter]}
                </span>
              </div>
            </div>
          </div>

          {/* ── Section: Edge Types ── */}
          {hasEdgeTypes && (
            <div className="px-3.5 pt-3 pb-3 border-t border-[#1e1e2a]">
              <div className="flex items-center gap-1.5 mb-2">
                <svg className="w-3 h-3 text-[#5a5a70]" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M2 8h12M10 4l4 4-4 4" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <span className="text-[10px] font-mono text-[#5a5a70] uppercase tracking-wider">
                  Relationship Types
                </span>
              </div>

              {edgeTypes.map((etype) => {
                const active = activeEdgeTypes.has(etype);
                return (
                  <button
                    key={etype}
                    onClick={() => onToggleEdgeType(etype)}
                    className="w-full flex items-center gap-2.5 px-1 py-1.5 text-left rounded-lg transition-all hover:bg-[#1c1c28]"
                    style={{ opacity: active ? 1 : 0.4 }}
                  >
                    {/* Edge-type indicator line */}
                    <div className="flex items-center gap-1 flex-none w-5">
                      <div
                        className="h-px rounded-full transition-all"
                        style={{
                          width: '100%',
                          backgroundColor: active ? '#a78bfa' : '#3a3a50',
                        }}
                      />
                    </div>
                    <span className="flex-1 text-xs text-[#e4e4ed] font-mono truncate">
                      {etype || '(unlabelled)'}
                    </span>
                    <span
                      className="flex-none w-1.5 h-1.5 rounded-full transition-all"
                      style={{
                        backgroundColor: active ? '#a78bfa' : 'transparent',
                        boxShadow:       active ? '0 0 4px #a78bfa' : 'none',
                      }}
                    />
                  </button>
                );
              })}

              {/* Edge type show/hide row */}
              <div className="flex gap-2 mt-2">
                <button
                  onClick={onShowAllEdges}
                  className="flex-1 text-[10px] font-mono text-[#8888a0] py-1.5 rounded-lg bg-[#16161f] border border-[#2a2a3a] hover:bg-[#1c1c28] hover:text-[#e4e4ed] transition-all text-center"
                >
                  All
                </button>
                <button
                  onClick={onHideAllEdges}
                  className="flex-1 text-[10px] font-mono text-[#8888a0] py-1.5 rounded-lg hover:bg-[#1c1c28] hover:text-[#e4e4ed] transition-all text-center"
                >
                  None
                </button>
              </div>
            </div>
          )}
        </div>

        {/* ── Node type action footer ── */}
        <div className="flex-none border-t border-[#2a2a3a] p-3 flex flex-col gap-2 bg-[#0a0a10]/60">
          <button
            onClick={onShowAll}
            className="w-full text-xs font-sans font-medium text-[#e4e4ed] py-2 px-3 rounded-lg bg-[#16161f] border border-[#2a2a3a] hover:bg-[#1c1c28] hover:border-[#7c3aed]/50 transition-all text-center shadow-sm"
          >
            Show All Types
          </button>
          <button
            onClick={onHideAll}
            className="w-full text-xs font-sans font-medium text-[#8888a0] py-2 px-3 rounded-lg hover:bg-[#1c1c28] hover:text-[#e4e4ed] transition-all text-center"
          >
            Hide All
          </button>
        </div>
      </div>
    </motion.div>
  );
}

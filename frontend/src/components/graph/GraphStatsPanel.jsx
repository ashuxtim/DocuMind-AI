import { useMemo } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { X, BarChart2 } from 'lucide-react';

const TYPE_COLORS = {
  Person: '#34D399',
  Organization: '#FBBF24',
  Statute: '#A78BFA',
  Date: '#22D3EE',
  Document: '#F472B6',
  Entity: '#94A3B8',
};

function fallbackColor(group) {
  return TYPE_COLORS[group] ?? '#94A3B8';
}

function truncate(str, n) {
  if (!str) return '';
  return str.length > n ? str.slice(0, n - 1) + '…' : str;
}

function SectionDivider() {
  return <div className="my-3 border-t border-[#2a2a3a]" />;
}

function StatCard({ label, value }) {
  return (
    <div className="flex-1 bg-[#0a0a10]/80 border border-[#2a2a3a] rounded-lg p-2.5 text-center min-w-0 shadow-sm">
      <div className="text-base font-bold font-mono text-[#e4e4ed] leading-tight">
        {value}
      </div>
      <div className="text-[10px] font-sans text-[#8888a0] mt-0.5 font-medium">
        {label}
      </div>
    </div>
  );
}

export function GraphStatsPanel({ isOpen, onClose, graph }) {
  const stats = useMemo(() => {
    if (!graph) return null;

    const order = graph.order;
    const size = graph.size;
    const avgConnections = order > 0 ? ((size * 2) / order).toFixed(1) : '0.0';

    const nodeList = [];
    graph.forEachNode((nodeId, attrs) => {
      nodeList.push({
        id: nodeId,
        label: attrs.label || nodeId,
        size: attrs.size || 1,
        color: attrs.color || '#94A3B8',
        group: attrs.group || 'Entity',
      });
    });
    nodeList.sort((a, b) => b.size - a.size);
    const topNodes = nodeList.slice(0, 10);
    const maxNodeSz = topNodes[0]?.size || 1;

    const typeCounts = {};
    nodeList.forEach(({ group }) => {
      typeCounts[group] = (typeCounts[group] || 0) + 1;
    });
    const typeEntries = Object.entries(typeCounts).sort(([, a], [, b]) => b - a);

    const edgeLabelCounts = {};
    graph.forEachEdge((edgeId, attrs) => {
      const lbl = attrs.label || 'related';
      edgeLabelCounts[lbl] = (edgeLabelCounts[lbl] || 0) + 1;
    });
    const edgeEntries = Object.entries(edgeLabelCounts)
      .sort(([, a], [, b]) => b - a)
      .slice(0, 8);
    const maxEdgeCount = edgeEntries[0]?.[1] || 1;

    return { order, size, avgConnections, topNodes, maxNodeSz, typeEntries, edgeEntries, maxEdgeCount };
  }, [graph]);

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          key="stats-panel"
          initial={{ x: 280 }}
          animate={{ x: 0 }}
          exit={{ x: 280 }}
          transition={{ type: 'spring', stiffness: 340, damping: 32 }}
          className="absolute top-16 right-3 bottom-14 z-20 flex flex-col bg-[#101018]/95 backdrop-blur-md border border-[#2a2a3a] rounded-xl shadow-glass overflow-hidden"
          style={{ width: 270 }}
        >
          {/* Header */}
          <div className="flex-none flex items-center justify-between px-3.5 py-3 border-b border-[#2a2a3a]">
            <div className="flex items-center gap-2">
              <BarChart2 className="w-4 h-4 text-[#7c3aed]" />
              <span className="text-xs font-semibold text-[#e4e4ed] font-sans tracking-wide">
                Graph Statistics
              </span>
            </div>
            <button
              onClick={onClose}
              className="flex items-center justify-center w-6 h-6 rounded-lg text-[#8888a0] hover:text-[#e4e4ed] hover:bg-[#1c1c28] transition-colors"
              title="Close stats"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Scrollable body */}
          <div className="flex-1 overflow-y-auto p-3.5 scrollbar-thin">
            {!stats ? (
              <p className="text-xs text-[#8888a0] text-center mt-6 font-mono">
                No graph data available.
              </p>
            ) : (
              <>
                {/* Summary cards */}
                <div className="flex gap-2 mb-1">
                  <StatCard label="Nodes" value={stats.order.toLocaleString()} />
                  <StatCard label="Edges" value={stats.size.toLocaleString()} />
                  <StatCard label="Avg Conn." value={stats.avgConnections} />
                </div>

                <SectionDivider />

                {/* Top entities */}
                <h3 className="text-[10px] font-bold text-[#8888a0] uppercase tracking-wider font-sans mb-2.5">
                  Top Entities by Connections
                </h3>
                <div className="flex flex-col gap-2">
                  {stats.topNodes.map((node) => {
                    const pct = Math.max(4, (node.size / stats.maxNodeSz) * 100);
                    return (
                      <div key={node.id}>
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-xs text-[#e4e4ed] font-sans font-medium truncate flex-1 pr-2">
                            {truncate(node.label, 20)}
                          </span>
                          <span
                            className="text-[10px] font-bold font-mono px-1.5 py-0.5 rounded-md text-[#06060a]"
                            style={{ backgroundColor: node.color }}
                          >
                            {Math.round(node.size)}
                          </span>
                        </div>
                        <div className="h-1.5 rounded-full bg-[#1e1e2a] overflow-hidden">
                          <div
                            className="h-full rounded-full transition-all duration-500"
                            style={{
                              width: `${pct}%`,
                              backgroundColor: node.color,
                            }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>

                <SectionDivider />

                {/* Node type breakdown */}
                <h3 className="text-[10px] font-bold text-[#8888a0] uppercase tracking-wider font-sans mb-2.5">
                  Entity Breakdown
                </h3>
                <div className="flex flex-col gap-2.5">
                  {stats.typeEntries.map(([type, count]) => {
                    const pct = Math.max(2, (count / stats.order) * 100);
                    const color = fallbackColor(type);
                    return (
                      <div key={type}>
                        <div className="flex items-center justify-between mb-1">
                          <div className="flex items-center gap-1.5">
                            <span
                              className="w-2 h-2 rounded-full flex-none shadow-sm"
                              style={{ backgroundColor: color }}
                            />
                            <span className="text-xs text-[#e4e4ed] font-sans font-medium">
                              {type}
                            </span>
                          </div>
                          <span className="text-xs font-mono text-[#8888a0]">
                            {count} <span className="text-[#5a5a70]">({pct.toFixed(0)}%)</span>
                          </span>
                        </div>
                        <div className="h-1.5 rounded-full bg-[#1e1e2a] overflow-hidden">
                          <div
                            className="h-full rounded-full transition-all duration-500 opacity-80"
                            style={{
                              width: `${pct}%`,
                              backgroundColor: color,
                            }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>

                <SectionDivider />

                {/* Relationship types */}
                <h3 className="text-[10px] font-bold text-[#8888a0] uppercase tracking-wider font-sans mb-2.5">
                  Relationship Types
                </h3>
                {stats.edgeEntries.length === 0 ? (
                  <p className="text-xs text-[#5a5a70] italic font-mono">No relationship labels found.</p>
                ) : (
                  <div className="flex flex-col gap-2">
                    {stats.edgeEntries.map(([relType, count]) => {
                      const pct = Math.max(3, (count / stats.maxEdgeCount) * 100);
                      return (
                        <div key={relType}>
                          <div className="flex items-center justify-between mb-1">
                            <span className="font-mono text-[11px] text-[#8888a0] truncate flex-1 pr-2">
                              {relType}
                            </span>
                            <span className="text-[10px] font-mono font-bold text-[#e4e4ed] bg-[#1e1e2a] px-1.5 py-0.5 rounded-md">
                              {count}
                            </span>
                          </div>
                          <div className="h-1.5 rounded-full bg-[#1e1e2a] overflow-hidden">
                            <div
                              className="h-full rounded-full bg-[#7c3aed]/70 transition-all duration-500"
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}


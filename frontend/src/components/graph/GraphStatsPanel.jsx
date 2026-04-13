import { useMemo } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { X, BarChart2 } from 'lucide-react';

// ── palette must mirror GraphPage / GraphFilterPanel ─────────────────────────
const TYPE_COLORS = {
  Person:       '#34D399',
  Organization: '#FBBF24',
  Statute:      '#A78BFA',
  Date:         '#22D3EE',
  Document:     '#F472B6',
  Entity:       '#94A3B8',
};

function fallbackColor(group) {
  return TYPE_COLORS[group] ?? '#94A3B8';
}

// ── tiny helpers ──────────────────────────────────────────────────────────────
function truncate(str, n) {
  if (!str) return '';
  return str.length > n ? str.slice(0, n - 1) + '…' : str;
}

function SectionDivider() {
  return <div style={{ borderTop: '1px solid rgba(100,116,139,0.25)', margin: '12px 0' }} />;
}

function StatCard({ label, value }) {
  return (
    <div style={{
      flex: 1,
      background: 'rgba(15,23,42,0.7)',
      border: '1px solid rgba(100,116,139,0.3)',
      borderRadius: 8,
      padding: '10px 8px',
      textAlign: 'center',
      minWidth: 0,
    }}>
      <div style={{ fontSize: 18, fontWeight: 700, color: '#f1f5f9', lineHeight: 1.2 }}>
        {value}
      </div>
      <div style={{ fontSize: 10, color: '#64748b', marginTop: 2, fontWeight: 500 }}>
        {label}
      </div>
    </div>
  );
}

// ── main component ────────────────────────────────────────────────────────────
export function GraphStatsPanel({ isOpen, onClose, graph }) {
  const stats = useMemo(() => {
    if (!graph) return null;

    const order = graph.order;        // total nodes
    const size  = graph.size;         // total edges
    const avgConnections = order > 0
      ? (size * 2 / order).toFixed(1)
      : '0.0';

    // ── top 10 nodes by size attribute (proxy for degree) ─────────────────
    const nodeList = [];
    graph.forEachNode((nodeId, attrs) => {
      nodeList.push({
        id:    nodeId,
        label: attrs.label || nodeId,
        size:  attrs.size  || 1,
        color: attrs.color || '#94A3B8',
        group: attrs.group || 'Entity',
      });
    });
    nodeList.sort((a, b) => b.size - a.size);
    const topNodes   = nodeList.slice(0, 10);
    const maxNodeSz  = topNodes[0]?.size || 1;

    // ── node type breakdown ────────────────────────────────────────────────
    const typeCounts = {};
    nodeList.forEach(({ group }) => {
      typeCounts[group] = (typeCounts[group] || 0) + 1;
    });
    const typeEntries = Object.entries(typeCounts).sort(([, a], [, b]) => b - a);

    // ── edge label (relationship type) breakdown ───────────────────────────
    const edgeLabelCounts = {};
    graph.forEachEdge((edgeId, attrs) => {
      const lbl = attrs.label || 'related';
      edgeLabelCounts[lbl] = (edgeLabelCounts[lbl] || 0) + 1;
    });
    const edgeEntries  = Object.entries(edgeLabelCounts).sort(([, a], [, b]) => b - a).slice(0, 8);
    const maxEdgeCount = edgeEntries[0]?.[1] || 1;

    return { order, size, avgConnections, topNodes, maxNodeSz, typeEntries, edgeEntries, maxEdgeCount };
  }, [graph]);

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          key="stats-panel"
          initial={{ x: 260 }}
          animate={{ x: 0 }}
          exit={{ x: 260 }}
          transition={{ type: 'spring', stiffness: 340, damping: 32 }}
          style={{
            position: 'absolute',
            top: 0,
            right: 0,
            width: 260,
            height: '100%',
            zIndex: 20,
            display: 'flex',
            flexDirection: 'column',
            background: 'rgba(2,6,23,0.95)',
            backdropFilter: 'blur(8px)',
            borderLeft: '1px solid rgba(100,116,139,0.3)',
          }}
        >
          {/* ── Header ── */}
          <div style={{
            flexShrink: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '12px 14px',
            borderBottom: '1px solid rgba(100,116,139,0.25)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
              <BarChart2 style={{ width: 14, height: 14, color: '#818cf8' }} />
              <span style={{ fontSize: 13, fontWeight: 600, color: '#f1f5f9', letterSpacing: '0.01em' }}>
                Graph Statistics
              </span>
            </div>
            <button
              onClick={onClose}
              style={{
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                padding: 4,
                borderRadius: 6,
                color: '#64748b',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                transition: 'color 0.15s',
              }}
              onMouseEnter={e => e.currentTarget.style.color = '#f1f5f9'}
              onMouseLeave={e => e.currentTarget.style.color = '#64748b'}
              title="Close stats"
            >
              <X style={{ width: 14, height: 14 }} />
            </button>
          </div>

          {/* ── Scrollable body ── */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '14px 14px 18px' }}>
            {!stats ? (
              <p style={{ fontSize: 12, color: '#64748b', textAlign: 'center', marginTop: 24 }}>
                No graph data yet.
              </p>
            ) : (
              <>
                {/* ── SECTION 1: Summary cards ── */}
                <div style={{ display: 'flex', gap: 6, marginBottom: 4 }}>
                  <StatCard label="Total Nodes" value={stats.order.toLocaleString()} />
                  <StatCard label="Total Edges" value={stats.size.toLocaleString()} />
                  <StatCard label="Avg Conn." value={stats.avgConnections} />
                </div>

                <SectionDivider />

                {/* ── SECTION 2: Top entities ── */}
                <h3 style={{ fontSize: 10, fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 9 }}>
                  Top Entities by Connections
                </h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                  {stats.topNodes.map((node, i) => {
                    const pct = Math.max(4, (node.size / stats.maxNodeSz) * 100);
                    return (
                      <div key={node.id}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 3 }}>
                          <span style={{ fontSize: 11, color: '#cbd5e1', fontWeight: 500, flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {truncate(node.label, 22)}
                          </span>
                          <span style={{
                            fontSize: 10,
                            fontWeight: 600,
                            color: '#0f172a',
                            background: node.color,
                            borderRadius: 10,
                            padding: '1px 6px',
                            marginLeft: 6,
                            flexShrink: 0,
                          }}>
                            {Math.round(node.size)}
                          </span>
                        </div>
                        <div style={{ height: 4, borderRadius: 4, background: 'rgba(100,116,139,0.2)', overflow: 'hidden' }}>
                          <div style={{
                            height: '100%',
                            width: `${pct}%`,
                            borderRadius: 4,
                            background: node.color,
                            transition: 'width 0.5s ease',
                          }} />
                        </div>
                      </div>
                    );
                  })}
                </div>

                <SectionDivider />

                {/* ── SECTION 3: Node type breakdown ── */}
                <h3 style={{ fontSize: 10, fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 9 }}>
                  Node Types
                </h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {stats.typeEntries.map(([type, count]) => {
                    const pct = Math.max(2, (count / stats.order) * 100);
                    const color = fallbackColor(type);
                    return (
                      <div key={type}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 3 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <span style={{
                              display: 'inline-block',
                              width: 7,
                              height: 7,
                              borderRadius: '50%',
                              background: color,
                              flexShrink: 0,
                            }} />
                            <span style={{ fontSize: 11, color: '#cbd5e1', fontWeight: 500 }}>
                              {type}
                            </span>
                          </div>
                          <span style={{ fontSize: 10, color: '#94a3b8', fontWeight: 600 }}>
                            {count} <span style={{ color: '#475569', fontWeight: 400 }}>({pct.toFixed(0)}%)</span>
                          </span>
                        </div>
                        <div style={{ height: 3, borderRadius: 3, background: 'rgba(100,116,139,0.18)', overflow: 'hidden' }}>
                          <div style={{
                            height: '100%',
                            width: `${pct}%`,
                            borderRadius: 3,
                            background: color,
                            opacity: 0.75,
                            transition: 'width 0.5s ease',
                          }} />
                        </div>
                      </div>
                    );
                  })}
                </div>

                <SectionDivider />

                {/* ── SECTION 4: Relationship types ── */}
                <h3 style={{ fontSize: 10, fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 9 }}>
                  Relationship Types
                </h3>
                {stats.edgeEntries.length === 0 ? (
                  <p style={{ fontSize: 11, color: '#475569', fontStyle: 'italic' }}>No edge labels found.</p>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                    {stats.edgeEntries.map(([relType, count]) => {
                      const pct = Math.max(3, (count / stats.maxEdgeCount) * 100);
                      return (
                        <div key={relType}>
                          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 3 }}>
                            <span style={{
                              fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                              fontSize: 10,
                              color: '#94a3b8',
                              flex: 1,
                              minWidth: 0,
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            }}>
                              {relType}
                            </span>
                            <span style={{
                              fontSize: 10,
                              fontWeight: 600,
                              color: '#cbd5e1',
                              marginLeft: 6,
                              background: 'rgba(100,116,139,0.2)',
                              borderRadius: 8,
                              padding: '1px 5px',
                              flexShrink: 0,
                            }}>
                              {count}
                            </span>
                          </div>
                          <div style={{ height: 3, borderRadius: 3, background: 'rgba(100,116,139,0.18)', overflow: 'hidden' }}>
                            <div style={{
                              height: '100%',
                              width: `${pct}%`,
                              borderRadius: 3,
                              background: 'rgba(148,163,184,0.6)',
                              transition: 'width 0.5s ease',
                            }} />
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

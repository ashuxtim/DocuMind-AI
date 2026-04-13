import { useState, useRef, useCallback } from 'react';
import { Network, ZoomIn, ZoomOut, Maximize2, RefreshCw } from 'lucide-react';
import { useGraphData } from '@/hooks/useGraphData';
import GraphExplorer from '@/components/graph/GraphExplorer';
import { Button } from '@/ui/button';
import { Input } from '@/ui/input';
import { Badge } from '@/ui/badge';

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
  const explorerRef = useRef(null);

  const handleSearchKeyDown = useCallback(
    (e) => {
      if (e.key === 'Enter') setCommittedSearch(searchValue);
    },
    [searchValue],
  );

  return (
    <div className="flex flex-col h-full bg-background">
      {/* ── Header ── */}
      <div className="flex-none border-b border-border px-4 py-3">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          {/* Title */}
          <div className="flex items-center gap-3 min-w-0">
            <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-primary/10">
              <Network className="w-4 h-4 text-primary" />
            </div>
            <div>
              <h1 className="text-sm font-semibold text-foreground leading-tight">
                Knowledge Graph
              </h1>
              <p className="text-xs text-muted-foreground leading-tight">
                Explore entities and relationships
              </p>
            </div>
          </div>

          {/* Color legend */}
          <div className="flex items-center gap-3 flex-wrap">
            {NODE_COLORS.map(({ label, color }) => (
              <span key={label} className="flex items-center gap-1 text-xs text-muted-foreground">
                <span
                  className="inline-block w-2 h-2 rounded-full flex-none"
                  style={{ backgroundColor: color }}
                />
                {label}
              </span>
            ))}
          </div>

          {/* Controls */}
          <div className="flex items-center gap-2">
            {/* Stats badges */}
            <Badge variant="secondary" className="text-xs tabular-nums">
              {nodeCount.toLocaleString()} nodes
            </Badge>
            <Badge variant="secondary" className="text-xs tabular-nums">
              {linkCount.toLocaleString()} edges
            </Badge>

            {/* Search */}
            <Input
              className="h-7 w-48 text-xs"
              placeholder="Search nodes…"
              value={searchValue}
              onChange={(e) => setSearchValue(e.target.value)}
              onKeyDown={handleSearchKeyDown}
            />

            {/* Camera controls */}
            <Button
              variant="outline"
              size="icon"
              className="h-7 w-7"
              title="Zoom in"
              onClick={() => explorerRef.current?.zoomIn()}
            >
              <ZoomIn className="w-3.5 h-3.5" />
            </Button>
            <Button
              variant="outline"
              size="icon"
              className="h-7 w-7"
              title="Zoom out"
              onClick={() => explorerRef.current?.zoomOut()}
            >
              <ZoomOut className="w-3.5 h-3.5" />
            </Button>
            <Button
              variant="outline"
              size="icon"
              className="h-7 w-7"
              title="Fit view"
              onClick={() => explorerRef.current?.fitView()}
            >
              <Maximize2 className="w-3.5 h-3.5" />
            </Button>

            {/* Refetch */}
            <Button
              variant="outline"
              size="icon"
              className="h-7 w-7"
              title="Reload graph"
              onClick={refetch}
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </Button>
          </div>
        </div>
      </div>

      {/* ── Canvas area ── */}
      <div className="flex-1 relative min-h-0">
        {loading && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 z-10 bg-background">
            <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
            <p className="text-sm text-muted-foreground">Loading knowledge graph…</p>
          </div>
        )}

        {error && !loading && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 z-10 bg-background">
            <p className="text-sm text-destructive">{error}</p>
            <Button variant="outline" size="sm" onClick={refetch}>
              <RefreshCw className="w-3.5 h-3.5 mr-2" />
              Retry
            </Button>
          </div>
        )}

        {/* Sigma needs a real pixel height — ensure parent chain has h-full */}
        {graph && !loading && !error && (
          <div className="w-full h-full">
            <GraphExplorer
              ref={explorerRef}
              graph={graph}
              search={committedSearch}
            />
          </div>
        )}
      </div>

      {/* ── Footer hint ── */}
      <div className="flex-none border-t border-border px-4 py-1.5">
        <p className="text-xs text-muted-foreground text-center">
          Click to focus · Search by name · Drag to pan · Scroll to zoom
        </p>
      </div>
    </div>
  );
}

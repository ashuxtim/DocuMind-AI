import { Network } from 'lucide-react';
import GraphExplorer from '@/components/graph/GraphExplorer';
import { Badge } from '@/ui/badge';
import { Card } from '@/ui/card';

export function GraphPage() {
  return (
    <div className="h-full flex flex-col bg-background">
      {/* Header */}
      <div className="px-6 py-4 border-b border-border bg-card">
        <div className="flex items-center justify-between max-w-7xl mx-auto">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-primary to-secondary flex items-center justify-center">
              <Network className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-semibold text-foreground">Knowledge Graph</h1>
              <p className="text-sm text-muted-foreground">
                Explore entities and relationships
              </p>
            </div>
          </div>

          {/* Legend */}
          <Card className="flex items-center gap-3 px-4 py-2">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-[#34D399]" />
              <span className="text-xs text-muted-foreground">Person</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-[#A78BFA]" />
              <span className="text-xs text-muted-foreground">Statute</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-[#FBBF24]" />
              <span className="text-xs text-muted-foreground">Organization</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-[#94A3B8]" />
              <span className="text-xs text-muted-foreground">Entity</span>
            </div>
          </Card>
        </div>
      </div>

      {/* Graph Canvas */}
      <div className="flex-1 overflow-hidden">
        <GraphExplorer />
      </div>

      {/* Instructions Footer */}
      <div className="px-6 py-3 border-t border-border bg-card">
        <div className="max-w-7xl mx-auto flex items-center justify-center gap-6 text-xs text-muted-foreground">
          <span>💡 Click nodes to focus</span>
          <span>·</span>
          <span>🔍 Search by entity name</span>
          <span>·</span>
          <span>🖱️ Drag to pan</span>
          <span>·</span>
          <span>⚡ Scroll to zoom</span>
        </div>
      </div>
    </div>
  );
}

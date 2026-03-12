import { motion } from 'framer-motion';
import { ZoomIn, ZoomOut, Maximize2, RotateCcw, Search } from 'lucide-react';
import { Button } from '@/ui/button';
import { Input } from '@/ui/input';
import { Card } from '@/ui/card';
import { Badge } from '@/ui/badge';

export function GraphControls({ 
  onZoomIn, 
  onZoomOut, 
  onFitView, 
  onReset,
  searchTerm,
  onSearchChange,
  onSearch,
  searchError,
  nodeCount,
  linkCount 
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -20 }}
      animate={{ opacity: 1, y: 0 }}
      className="absolute top-4 left-4 right-4 z-10 pointer-events-none"
    >
      <div className="flex items-center justify-between gap-4 max-w-7xl mx-auto">
        {/* Search */}
        <Card className="flex items-center gap-2 p-2 pointer-events-auto flex-1 max-w-md">
          <Search className="w-4 h-4 text-muted-foreground ml-2" />
          <Input
            type="text"
            placeholder="Search nodes..."
            value={searchTerm}
            onChange={(e) => onSearchChange(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && onSearch()}
            className={`border-0 focus-visible:ring-0 ${searchError ? 'text-destructive' : ''}`}
          />
          {searchError && (
            <Badge variant="destructive" className="mr-2">Not found</Badge>
          )}
        </Card>

        {/* Stats */}
        <Card className="flex items-center gap-3 px-4 py-2 pointer-events-auto">
          <Badge variant="outline">{nodeCount} nodes</Badge>
          <Badge variant="outline">{linkCount} edges</Badge>
        </Card>

        {/* Controls */}
        <Card className="flex items-center gap-1 p-1 pointer-events-auto">
          <Button
            variant="ghost"
            size="icon"
            onClick={onZoomIn}
            title="Zoom In"
          >
            <ZoomIn className="w-4 h-4" />
          </Button>
          
          <Button
            variant="ghost"
            size="icon"
            onClick={onZoomOut}
            title="Zoom Out"
          >
            <ZoomOut className="w-4 h-4" />
          </Button>
          
          <Button
            variant="ghost"
            size="icon"
            onClick={onFitView}
            title="Fit View"
          >
            <Maximize2 className="w-4 h-4" />
          </Button>
          
          <Button
            variant="ghost"
            size="icon"
            onClick={onReset}
            title="Reset"
          >
            <RotateCcw className="w-4 h-4" />
          </Button>
        </Card>
      </div>
    </motion.div>
  );
}

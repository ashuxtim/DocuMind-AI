import { ZoomIn, ZoomOut, Maximize2, Focus, RotateCcw, Play, Pause } from 'lucide-react';
import { Button } from '@/ui/button';

export function GraphControlsWidget({
  onZoomIn,
  onZoomOut,
  onFitView,
  onFocusSelected,
  onClearSelection,
  onToggleLayout,
  selectedNode,
  isLayoutRunning,
}) {
  return (
    <div className="absolute bottom-4 right-4 z-20 flex flex-col gap-1.5 p-1.5 rounded-xl bg-[#101018]/85 backdrop-blur-md border border-[#2a2a3a] shadow-glass">

      {/* ── Zoom controls ── */}
      <Button
        variant="ghost"
        size="icon"
        className="h-8 w-8 rounded-lg text-[#e4e4ed] hover:bg-[#1c1c28] hover:text-white transition-all"
        title="Zoom in"
        onClick={onZoomIn}
      >
        <ZoomIn className="w-4 h-4" />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        className="h-8 w-8 rounded-lg text-[#e4e4ed] hover:bg-[#1c1c28] hover:text-white transition-all"
        title="Zoom out"
        onClick={onZoomOut}
      >
        <ZoomOut className="w-4 h-4" />
      </Button>

      <div className="w-full h-px bg-[#1e1e2a]" />

      {/* ── Fit view ── */}
      <Button
        variant="ghost"
        size="icon"
        className="h-8 w-8 rounded-lg text-[#e4e4ed] hover:bg-[#1c1c28] hover:text-white transition-all"
        title="Fit graph to screen"
        onClick={onFitView}
      >
        <Maximize2 className="w-4 h-4" />
      </Button>

      <div className="w-full h-px bg-[#1e1e2a]" />

      {/* ── Layout Play / Pause (GitNexus style) ── */}
      <Button
        variant="ghost"
        size="icon"
        className={`h-8 w-8 rounded-lg transition-all ${
          isLayoutRunning
            ? 'animate-pulse bg-[#7c3aed] text-white border border-[#7c3aed] shadow-glow hover:bg-[#6d28d9]'
            : 'text-[#e4e4ed] hover:bg-[#1c1c28] hover:text-white'
        }`}
        title={isLayoutRunning ? 'Stop layout' : 'Run layout'}
        onClick={onToggleLayout}
      >
        {isLayoutRunning ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
      </Button>

      {/* ── Contextual: Focus + Clear (only when a node is selected) ── */}
      {selectedNode && (
        <>
          <div className="w-full h-px bg-[#1e1e2a]" />

          {/* Focus on selected — accent color */}
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 rounded-lg text-[#7c3aed] border border-[#7c3aed]/30 bg-[#7c3aed]/10 hover:bg-[#7c3aed]/20 hover:text-[#a78bfa] transition-all"
            title={`Re-center on: ${selectedNode}`}
            onClick={onFocusSelected}
          >
            <Focus className="w-4 h-4" />
          </Button>

          {/* Clear selection — neutral */}
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 rounded-lg text-[#e4e4ed] hover:bg-[#1c1c28] hover:text-white transition-all"
            title="Clear selection"
            onClick={onClearSelection}
          >
            <RotateCcw className="w-4 h-4" />
          </Button>
        </>
      )}
    </div>
  );
}

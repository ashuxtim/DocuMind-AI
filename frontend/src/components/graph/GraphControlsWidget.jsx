import { ZoomIn, ZoomOut, Maximize2, RotateCcw } from 'lucide-react';
import { Button } from '@/ui/button';

export function GraphControlsWidget({ onZoomIn, onZoomOut, onFitView, onResetView }) {
  return (
    <div className="absolute bottom-4 right-4 z-20 flex flex-col gap-1.5 p-1.5 rounded-xl bg-[#101018]/85 backdrop-blur-md border border-[#2a2a3a] shadow-glass">
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
      <Button
        variant="ghost"
        size="icon"
        className="h-8 w-8 rounded-lg text-[#e4e4ed] hover:bg-[#1c1c28] hover:text-white transition-all"
        title="Fit view to screen"
        onClick={onFitView}
      >
        <Maximize2 className="w-4 h-4" />
      </Button>
      {onResetView && (
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 rounded-lg text-[#e4e4ed] hover:bg-[#1c1c28] hover:text-white transition-all"
          title="Reset camera orientation"
          onClick={onResetView}
        >
          <RotateCcw className="w-4 h-4" />
        </Button>
      )}
    </div>
  );
}

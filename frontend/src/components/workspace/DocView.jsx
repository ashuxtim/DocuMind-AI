import { ArrowLeft } from 'lucide-react';
import { useWorkspace } from '@/contexts/WorkspaceContext';
import DocViewer from './DocViewer';
import DocChat from './DocChat';

/**
 * DocView — Screen 2.
 * Split layout: DocViewer (left 45%) + DocChat (right flex-1).
 */
export default function DocView() {
  const { activeDoc, clearActiveDoc } = useWorkspace();

  return (
    <div className="h-full flex flex-col bg-background">
      {/* ── Top bar ── */}
      <div className="h-12 flex items-center gap-3 px-4 border-b border-border bg-card flex-shrink-0">
        <button
          onClick={clearActiveDoc}
          className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          All documents
        </button>
        <div className="w-px h-4 bg-border" />
        <span className="text-sm font-medium text-foreground truncate">
          {activeDoc}
        </span>
      </div>

      {/* ── Split panel ── */}
      <div className="flex-1 flex overflow-hidden">
        <DocViewer filename={activeDoc} />
        <DocChat />
      </div>
    </div>
  );
}

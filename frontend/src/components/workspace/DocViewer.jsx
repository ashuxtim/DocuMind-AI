import { FileText } from 'lucide-react';
import { Button } from '@/ui/button';
import { useWorkspace } from '@/contexts/WorkspaceContext';
import PDFViewer from './PDFViewer';

/**
 * DocViewer — Left panel of Screen 2.
 * Delegates PDF rendering to PDFViewer, shows a fallback for other types.
 *
 * Props:
 *   filename — the document filename to display
 */
export default function DocViewer({ filename }) {
  const { pdfViewerRef } = useWorkspace();
  const ext = filename.split('.').pop().toLowerCase();
  const isPDF = ext === 'pdf';

  return (
    <div className="w-[45%] flex-shrink-0 flex flex-col border-r border-border bg-muted/20 h-full">
      {/* ── Filename header ── */}
      <div className="h-10 flex items-center px-4 border-b border-border bg-card flex-shrink-0 gap-2">
        <FileText className="w-3.5 h-3.5 text-muted-foreground flex-shrink-0" />
        <span className="text-xs text-muted-foreground truncate" title={filename}>
          {filename}
        </span>
      </div>

      {/* ── Content ── */}
      {isPDF ? (
        <div className="flex-1 min-h-0 overflow-hidden">
          <PDFViewer ref={pdfViewerRef} filename={filename} />
        </div>
      ) : (
        <div className="flex-1 flex flex-col items-center justify-center gap-4">
          <FileText className="w-12 h-12 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            {ext === 'doc' || ext === 'docx'
              ? "Word documents can't be previewed"
              : "This file type can't be previewed"}
          </p>
          <a href={`/api/uploads/${filename}`} download={filename}>
            <Button variant="outline" size="sm">
              Download file
            </Button>
          </a>
        </div>
      )}
    </div>
  );
}

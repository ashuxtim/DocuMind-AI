import { useState, useRef, useMemo, useCallback } from 'react';
import { Upload, FileText } from 'lucide-react';

import { useWorkspace } from '@/contexts/WorkspaceContext';
import useFuzzySearch from '@/hooks/useFuzzySearch';

import DocumentCard from './DocumentCard';
import DocumentSearch from './DocumentSearch';
import { SkeletonCard } from '@/components/shared/SkeletonCard';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/ui/dialog';
import { Button } from '@/ui/button';

/**
 * DocumentGrid — Screen 1 of the workspace.
 * Full document library with search, sort, upload, preview, and grid layout.
 *
 * Props:
 *   onDocOpen — (filename: string) => void
 */
export default function DocumentGrid({ onDocOpen }) {
  const {
    documents,
    docsLoading,
    deleteDocument,
    setActiveDoc,
    uploadDocument,
  } = useWorkspace();

  // ── Local state ──
  const [query, setQuery] = useState('');
  const [sortBy, setSortBy] = useState('date-desc');
  const [previewDoc, setPreviewDoc] = useState(null);
  const fileInputRef = useRef(null);

  // ── Search + sort pipeline ──
  const filtered = useFuzzySearch(documents, query, 'filename');

  const sorted = useMemo(() => {
    return [...filtered].sort((a, b) => {
      switch (sortBy) {
        case 'date-asc':
          return new Date(a.uploaded_at) - new Date(b.uploaded_at);
        case 'date-desc':
          return new Date(b.uploaded_at) - new Date(a.uploaded_at);
        case 'name-asc':
          return a.filename.localeCompare(b.filename);
        case 'name-desc':
          return b.filename.localeCompare(a.filename);
        case 'size-desc':
          return (b.size || 0) - (a.size || 0);
        default:
          return new Date(b.uploaded_at) - new Date(a.uploaded_at);
      }
    });
  }, [filtered, sortBy]);

  // ── Handlers ──
  const handleFileInput = useCallback(
    async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      await uploadDocument(file);
      e.target.value = '';
    },
    [uploadDocument]
  );

  const handleDelete = useCallback(
    (filename) => {
      if (window.confirm(`Delete "${filename}"?`)) {
        deleteDocument(filename);
      }
    },
    [deleteDocument]
  );

  const handlePreview = useCallback((filename) => {
    setPreviewDoc(filename);
  }, []);

  const handleOpen = useCallback(
    (filename) => {
      setActiveDoc(filename);
      onDocOpen?.(filename);
    },
    [setActiveDoc, onDocOpen]
  );

  // ── Render ──
  return (
    <div className="h-full flex flex-col bg-background">
      {/* ── Top header bar ── */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-border flex-shrink-0">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Documents</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Your knowledge base
          </p>
        </div>
        <button
          onClick={() => fileInputRef.current?.click()}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors"
        >
          <Upload className="w-4 h-4" />
          Upload document
        </button>
        <input
          type="file"
          accept=".pdf,.docx,.txt,.md,.html,.htm"
          onChange={handleFileInput}
          className="hidden"
          ref={fileInputRef}
        />
      </div>

      {/* ── Search + sort bar ── */}
      <div className="px-6 py-3 border-b border-border flex-shrink-0">
        <DocumentSearch
          query={query}
          onQueryChange={setQuery}
          sortBy={sortBy}
          onSortChange={setSortBy}
          totalCount={documents.length}
          filteredCount={sorted.length}
        />
      </div>

      {/* ── Grid area ── */}
      <div className="flex-1 overflow-y-auto px-6 py-6">
        {/* Loading state */}
        {docsLoading && (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
            {[...Array(6)].map((_, i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
        )}

        {/* Empty state — no documents at all */}
        {!docsLoading && documents.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full min-h-[400px] gap-4 text-center">
            <div className="w-20 h-20 rounded-full bg-muted flex items-center justify-center">
              <FileText className="w-10 h-10 text-muted-foreground/50" />
            </div>
            <div>
              <h3 className="text-lg font-medium text-foreground mb-1">
                No documents yet
              </h3>
              <p className="text-sm text-muted-foreground max-w-xs">
                Upload your first PDF or Word document to get started
              </p>
            </div>
            <button
              onClick={() => fileInputRef.current?.click()}
              className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium"
            >
              <Upload className="w-4 h-4" />
              Upload document
            </button>
          </div>
        )}

        {/* Empty state — search returned nothing */}
        {!docsLoading && documents.length > 0 && sorted.length === 0 && (
          <div className="flex flex-col items-center justify-center h-64 gap-3 text-center">
            <p className="text-muted-foreground">
              No documents match &quot;{query}&quot;
            </p>
          </div>
        )}

        {/* Document grid */}
        {!docsLoading && sorted.length > 0 && (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
            {sorted.map((doc) => (
              <DocumentCard
                key={doc.filename}
                doc={doc}
                onOpen={handleOpen}
                onDelete={handleDelete}
                onPreview={handlePreview}
              />
            ))}
          </div>
        )}
      </div>

      {/* ── PDF Preview Dialog ── */}
      {previewDoc && (
        <Dialog open={!!previewDoc} onOpenChange={() => setPreviewDoc(null)}>
          <DialogContent className="max-w-4xl h-[80vh] flex flex-col p-0 gap-0 overflow-hidden">
            <DialogHeader className="p-4 border-b border-border">
              <DialogTitle className="flex items-center gap-2">
                <FileText className="w-4 h-4" />
                {previewDoc}
              </DialogTitle>
            </DialogHeader>
            <div className="flex-1 bg-muted">
              {previewDoc.toLowerCase().endsWith('.docx') ? (
                <div className="flex flex-col items-center justify-center h-full gap-4">
                  <FileText className="w-12 h-12 text-muted-foreground" />
                  <p className="text-muted-foreground">
                    Preview not available for Word documents
                  </p>
                  <a href={`/api/uploads/${previewDoc}`} download={previewDoc}>
                    <Button variant="outline">Download File</Button>
                  </a>
                </div>
              ) : (
                <iframe
                  src={`/api/uploads/${previewDoc}`}
                  className="w-full h-full"
                  title={previewDoc}
                />
              )}
            </div>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}

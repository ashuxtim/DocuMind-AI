import { useState } from 'react';
import { FileText, X, File } from 'lucide-react'; // Added X and File icons
import { useDocumentContext } from '@/contexts/DocumentContext';
import { UploadZone } from '@/components/documents/UploadZone';
import { SortControls } from '@/components/documents/SortControls';
// REMOVED: ProcessingIndicator (we will build a better one inline)
// import { ProcessingIndicator } from '@/components/documents/ProcessingIndicator';
import { DocumentSelector } from '@/components/documents/DocumentSelector';
import { FileProcessing } from '@/components/shared/FileProcessing'; // <--- NEW IMPORT
import { SkeletonList } from '@/components/shared/SkeletonCard';
import { Card } from '@/ui/card';
import { Separator } from '@/ui/separator';
import { Badge } from '@/ui/badge';
import { Button } from '@/ui/button'; // Needed for Cancel button
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/ui/dialog';

const API_BASE_URL = 'http://127.0.0.1:8000';

export function DocumentsPage() {
  const {
    documents,
    selectedDocs,
    loading,
    uploadingFiles,
    handleUpload,
    handleDelete,
    handleCancel,
  } = useDocumentContext();

  const [activePdf, setActivePdf] = useState(null);
  const [sortBy, setSortBy] = useState('date-desc');

  // REMOVED: getProgress function (no longer needed, the Hook handles it)

  const handleView = (filename) => {
    setActivePdf(filename);
  };

  if (loading) {
    return (
      <div className="h-full p-6">
        <SkeletonList count={6} />
      </div>
    );
  }

  return (
    <div className="h-full flex overflow-hidden">
      {/* Left Panel - Document List */}
      <div className="w-96 flex flex-col flex-shrink-0">
        {/* Header Section */}
        <div className="p-4 flex-shrink-0 bg-card border-r border-border">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-foreground">Documents</h2>
            <Badge variant="outline">{documents.length}</Badge>
          </div>
          
          <SortControls 
            onSortChange={setSortBy}
            currentSort={sortBy}
          />
        </div>

        <Separator className="flex-shrink-0" />

        {/* List Section */}
        <div className="flex-1 overflow-hidden flex flex-col">
           {/* This Sidebar component already uses FileProcessing internally now! */}
           <DocumentSelector 
             isOpen={true} 
             onView={handleView}
             onDelete={handleDelete}
             compact={false} 
           />
        </div>
      </div>

      {/* Right Panel - Upload & Processing */}
      <div className="flex-1 p-6 overflow-auto bg-background min-w-0">
        <div className="max-w-4xl mx-auto space-y-6">
          <UploadZone onUpload={handleUpload} />

          {/* FIX: Processing Files Queue with Smooth Animation */}
          {uploadingFiles.length > 0 && (
            <Card className="p-4 border-amber-200/50 bg-amber-50/10 dark:border-amber-900/30">
              <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-amber-500 animate-pulse" />
                Processing Queue ({uploadingFiles.length})
              </h3>
              
              <div className="space-y-3">
                {uploadingFiles.map(filename => (
                  <div key={filename} className="bg-card border border-border rounded-lg p-3 shadow-sm">
                    {/* Top Row: Icon, Name, Cancel */}
                    <div className="flex items-center gap-3 mb-2">
                      <div className="w-8 h-8 rounded bg-muted flex items-center justify-center flex-shrink-0">
                        <File className="w-4 h-4 text-muted-foreground" />
                      </div>
                      
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate" title={filename}>
                          {filename}
                        </p>
                      </div>

                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6 text-muted-foreground hover:text-destructive"
                        onClick={() => handleCancel(filename)}
                        title="Cancel Upload"
                      >
                        <X className="w-4 h-4" />
                      </Button>
                    </div>

                    {/* Bottom Row: The Smooth Progress Bar */}
                    {/* We pass status='processing' so it animates 0 -> 90% */}
                    <FileProcessing status="processing" filename={filename} />
                  </div>
                ))}
              </div>
            </Card>
          )}

          {/* Selected Documents Info Panel */}
          {selectedDocs.length > 0 && (
            <Card className="p-6 border-primary/20 bg-primary/5">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-lg font-semibold text-foreground mb-1">
                    {selectedDocs.length} Document{selectedDocs.length > 1 ? 's' : ''} Selected
                  </h3>
                  <p className="text-sm text-muted-foreground">
                    You can manage these documents or go to the Chat/Summary pages to work with them.
                  </p>
                </div>
                <div className="h-12 w-12 rounded-full bg-primary/20 flex items-center justify-center">
                  <FileText className="w-6 h-6 text-primary" />
                </div>
              </div>
            </Card>
          )}
        </div>
      </div>

      {/* Document Preview Modal */}
      {activePdf && (
        <Dialog open={!!activePdf} onOpenChange={() => setActivePdf(null)}>
          <DialogContent className="max-w-4xl h-[80vh] flex flex-col p-0 gap-0 overflow-hidden">
            <DialogHeader className="p-4 border-b border-border bg-card">
              <DialogTitle className="flex items-center gap-2">
                <FileText className="w-5 h-5 text-primary" />
                {activePdf}
              </DialogTitle>
            </DialogHeader>
            <div className="flex-1 bg-muted">
              <iframe
                src={`${API_BASE_URL}/uploads/${activePdf}`}
                className="w-full h-full"
                title={activePdf}
              />
            </div>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
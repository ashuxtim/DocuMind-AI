import { useState } from 'react';
import { Sparkles, FileText, PanelLeftClose, PanelLeft, Bot, Loader2 } from 'lucide-react';
import { useDocumentContext } from '@/contexts/DocumentContext';
import { useSummaryContext } from '@/contexts/SummaryContext';
import { DocumentSelector } from '@/components/documents/DocumentSelector';
import { SummaryCard } from '@/components/summary/SummaryCard';
import { Button } from '@/ui/button';
import { Badge } from '@/ui/badge';
import { SkeletonList } from '@/components/shared/SkeletonCard';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/ui/dialog';
import { Card } from '@/ui/card';
import { AnimatePresence, motion } from 'framer-motion';

const API_BASE_URL = 'http://127.0.0.1:8000';

export function SummaryPage() {
  const { documents, selectedDocs, loading, handleDelete } = useDocumentContext();
  const { generateSummary, loading: summaryLoading, summaries } = useSummaryContext();
  
  const [previewDoc, setPreviewDoc] = useState(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  const displayDocs = selectedDocs.length > 0
    ? documents.filter(doc => selectedDocs.includes(doc.filename))
    : [];

  const handleViewDocument = (filename) => {
    setPreviewDoc(filename);
  };

  const handleGenerate = async (filename) => {
    await generateSummary(filename);
  };

  if (loading) {
    return (
      <div className="h-full p-6">
        <SkeletonList count={6} />
      </div>
    );
  }

  return (
    <div className="h-full flex bg-background overflow-hidden">
      <AnimatePresence mode="wait">
        {isSidebarOpen && (
          <div className="h-full border-r border-border">
            <DocumentSelector
              isOpen={true}
              onClose={() => setIsSidebarOpen(false)}
              onView={handleViewDocument}
              onDelete={handleDelete}
              compact={false}
            />
          </div>
        )}
      </AnimatePresence>

      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="px-6 py-4 border-b border-border bg-card flex-shrink-0">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              {!isSidebarOpen && (
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setIsSidebarOpen(true)}
                >
                  <PanelLeft className="w-5 h-5" />
                </Button>
              )}
              <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-secondary to-primary flex items-center justify-center">
                <Sparkles className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className="text-xl font-semibold text-foreground">Document Summaries</h1>
                <p className="text-sm text-muted-foreground">
                  AI-generated executive reports
                </p>
              </div>
            </div>
            <Badge variant="secondary" className="text-lg px-4 py-2">
              {displayDocs.length} selected
            </Badge>
          </div>
        </div>

        {/* Scrollable Report Area */}
        <div className="flex-1 overflow-y-auto p-8">
          {/* FIX: Changed to single column, full width, with max-width for readability */}
          <div className="flex flex-col gap-8 w-full max-w-5xl mx-auto">
            {displayDocs.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-[60vh] text-center opacity-60">
                <div className="w-24 h-24 bg-muted rounded-full flex items-center justify-center mb-6">
                  <FileText className="w-10 h-10 text-muted-foreground" />
                </div>
                <h3 className="text-xl font-semibold mb-2">No Documents Selected</h3>
                <p className="text-muted-foreground max-w-md">
                  Select documents from the sidebar to generate a full report.
                </p>
              </div>
            ) : (
              displayDocs.map((doc) => {
                const isGenerating = summaryLoading.includes(doc.filename);
                const summaryData = summaries.get(doc.filename);
                const summaryText = summaryData?.content;
                
                if (summaryText) {
                  return (
                    <SummaryCard
                      key={doc.filename}
                      filename={doc.filename}
                      summary={summaryText}
                      createdAt={summaryData.timestamp || doc.completed_at}
                      fileType={doc.type}
                      onViewDocument={handleViewDocument}
                    />
                  );
                } else {
                  return (
                    <motion.div 
                      key={doc.filename}
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="w-full"
                    >
                      <Card className="border-dashed border-2 p-12 flex flex-col items-center justify-center text-center bg-muted/10">
                        <Bot className="w-12 h-12 text-primary mb-4" />
                        <h3 className="text-xl font-semibold mb-2">{doc.filename}</h3>
                        <p className="text-muted-foreground mb-6 max-w-md">
                          Ready to process. Generate a comprehensive summary for this document.
                        </p>
                        <Button 
                          size="lg"
                          onClick={() => handleGenerate(doc.filename)}
                          disabled={isGenerating}
                        >
                          {isGenerating ? (
                            <>
                              <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                              Generating Report...
                            </>
                          ) : (
                            <>
                              <Sparkles className="w-5 h-5 mr-2" />
                              Generate Summary
                            </>
                          )}
                        </Button>
                      </Card>
                    </motion.div>
                  );
                }
              })
            )}
          </div>
        </div>
      </div>

      {/* Preview Modal */}
      {previewDoc && (
        <Dialog open={!!previewDoc} onOpenChange={() => setPreviewDoc(null)}>
          <DialogContent className="max-w-4xl h-[80vh] flex flex-col p-0 gap-0 overflow-hidden">
            <DialogHeader className="p-4 border-b border-border bg-card">
              <DialogTitle className="flex items-center gap-2">
                <FileText className="w-5 h-5 text-primary" />
                {previewDoc}
              </DialogTitle>
            </DialogHeader>
            <div className="flex-1 bg-muted">
              <iframe
                src={`${API_BASE_URL}/uploads/${previewDoc}`}
                className="w-full h-full"
                title={previewDoc}
              />
            </div>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
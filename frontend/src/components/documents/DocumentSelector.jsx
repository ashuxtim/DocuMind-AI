import { useState, useMemo } from 'react';
import { motion } from 'framer-motion';
import { Search, FileText, CheckCircle, ChevronRight, X, Eye, Trash2 } from 'lucide-react';
import { Input } from '@/ui/input';
import { Button } from '@/ui/button';
import { Badge } from '@/ui/badge';
import { ScrollArea } from '@/ui/scroll-area';
import { Separator } from '@/ui/separator';
import { Card } from '@/ui/card';
import { useDocumentContext } from '@/contexts/DocumentContext';
import { smartSearch } from '@/lib/smartSearch';
import { cn } from '@/lib/utils';
import { FileProcessing } from '@/components/shared/FileProcessing';

export function DocumentSelector({ isOpen, onClose, compact = false, onView, onDelete }) {
  const { documents, selectedDocs, toggleSelection, clearSelection, selectAll } = useDocumentContext();
  const [searchTerm, setSearchTerm] = useState('');

  // Smart filtered documents
  const filteredDocs = useMemo(() => {
    // We show all documents here, not just completed ones, so users can see processing status if needed
    // But typically we want to select completed ones for chat. 
    // Let's keep it to 'completed' for selection safety, or all if you want to manage them.
    // Based on "Management" requirement, let's show ALL, but disable selection for processing ones.
    return smartSearch(documents, searchTerm);
  }, [documents, searchTerm]);

  if (!isOpen) return null;

  return (
    <motion.div
      initial={{ x: compact ? 0 : -320, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: compact ? 0 : -320, opacity: 0 }}
      transition={{ type: 'spring', stiffness: 300, damping: 30 }}
      className={cn(
        "bg-card border-r border-border flex flex-col h-full", // <--- FIX: Added h-full
        compact ? "w-80" : "w-96"
      )}
    >
      {/* Header */}
      <div className="p-4 border-b border-border flex-shrink-0">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-foreground">Select Documents</h3>
          {onClose && (
            <Button variant="ghost" size="icon" onClick={onClose} className="h-7 w-7">
              <X className="w-4 h-4" />
            </Button>
          )}
        </div>

        {/* Search */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            type="text"
            placeholder="Search documents..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="pl-9"
          />
        </div>

        {/* Selection Info */}
        <div className="flex items-center justify-between mt-3 text-xs">
          <span className="text-muted-foreground">
            {selectedDocs.length} of {filteredDocs.length} selected
          </span>
          <div className="flex gap-1">
            {selectedDocs.length > 0 && (
              <Button variant="ghost" size="sm" onClick={clearSelection} className="h-6 text-xs">
                Clear
              </Button>
            )}
            <Button variant="ghost" size="sm" onClick={selectAll} className="h-6 text-xs">
              Select All
            </Button>
          </div>
        </div>
      </div>

      <Separator />

      {/* Document List */}
      <ScrollArea className="flex-1">
        <div className="p-2 space-y-1">
          {filteredDocs.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <FileText className="w-8 h-8 text-muted-foreground mb-2" />
              <p className="text-sm text-muted-foreground">
                {searchTerm ? 'No matches found' : 'No documents available'}
              </p>
            </div>
          ) : (
            filteredDocs.map((doc, index) => {
              const isSelected = selectedDocs.includes(doc.filename);
              const isCompleted = doc.status === 'completed';
              
              return (
                <motion.div
                  key={doc.filename}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: index * 0.02 }}
                  className={cn(
                    "group w-full flex items-center gap-2 p-2 rounded-lg transition-smooth border",
                    isSelected 
                      ? "bg-primary/10 border-primary/50" 
                      : "hover:bg-muted border-transparent"
                  )}
                >
                  {/* Selection Click Area */}
                  <button
                    onClick={() => isCompleted && toggleSelection(doc.filename)}
                    disabled={!isCompleted}
                    className="flex items-center gap-3 flex-1 min-w-0 text-left"
                  >
                    {/* Checkbox */}
                    <div
                      className={cn(
                        "w-4 h-4 rounded border-2 flex items-center justify-center flex-shrink-0 transition-colors",
                        isSelected 
                          ? "bg-primary border-primary" 
                          : "border-muted-foreground group-hover:border-primary/70"
                      )}
                    >
                      {isSelected && <CheckCircle className="w-3 h-3 text-white" />}
                    </div>

                    {/* File Icon */}
                    <div className={cn(
                      "w-8 h-8 rounded flex items-center justify-center flex-shrink-0",
                      isSelected ? "bg-primary/20" : "bg-muted"
                    )}>
                      <FileText className={cn("w-4 h-4", isSelected ? "text-primary" : "text-muted-foreground")} />
                    </div>

                    {/* Filename & Info */}
                    <div className="flex-1 min-w-0">
                      <p 
                        className={cn(
                          "text-sm truncate transition-colors",
                          isSelected ? "text-primary font-medium" : "text-foreground",
                          !isCompleted && "text-muted-foreground italic"
                        )}
                        title={doc.filename}
                      >
                         {doc.filename}
                      </p>
                      <FileProcessing status={doc.status} filename={doc.filename} />
                    </div>
                  </button>

                  {/* Actions (View & Delete) - Only show if completed/available */}
                  {isCompleted && (
                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      {onView && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-muted-foreground hover:text-primary"
                          onClick={(e) => {
                            e.stopPropagation();
                            onView(doc.filename);
                          }}
                          title="View Document"
                        >
                          <Eye className="w-3.5 h-3.5" />
                        </Button>
                      )}
                      
                      {onDelete && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-muted-foreground hover:text-destructive"
                          onClick={(e) => {
                            e.stopPropagation();
                            onDelete(doc.filename);
                          }}
                          title="Delete Document"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </Button>
                      )}
                    </div>
                  )}
                </motion.div>
              );
            })
          )}
        </div>
      </ScrollArea>

      {/* Footer Badge */}
      {selectedDocs.length > 0 && (
        <div className="p-4 border-t border-border flex-shrink-0">
          <Card className="p-3 bg-primary/5 border-primary/20">
            <div className="flex items-center justify-between">
              <span className="text-sm text-foreground">Ready to process</span>
              <Badge variant="default">{selectedDocs.length} docs</Badge>
            </div>
          </Card>
        </div>
      )}
    </motion.div>
  );
}
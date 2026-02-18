import { useState, useMemo, useRef } from 'react';
import { motion } from 'framer-motion';
import { Virtuoso } from 'react-virtuoso';
import { Search, FileText, Trash2, Eye, CheckCircle, Clock, XCircle } from 'lucide-react';
import { Input } from '@/ui/input';
import { Button } from '@/ui/button';
import { Badge } from '@/ui/badge';
import { Card } from '@/ui/card';
import { Separator } from '@/ui/separator';
import SummarizeButton from '../summary/SummarizeButton';
import { smartSearch } from '@/lib/smartSearch'; // NEW IMPORT
import { cn } from '@/lib/utils';

export default function DocumentList({ 
  documents, 
  selectedDocs, 
  activePdf, 
  onSelect, 
  onToggleSelection, 
  onDelete,
  onSummaryReceived 
}) {
  const [searchTerm, setSearchTerm] = useState('');
  const [focusedIndex, setFocusedIndex] = useState(-1);
  const virtuosoRef = useRef(null);

  // SMART SEARCH - replaces old filter logic
  const filteredDocs = useMemo(() => {
    return smartSearch(documents, searchTerm);
  }, [documents, searchTerm]);

  // ... rest of the component stays the same ...
  const handleKeyDown = (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setFocusedIndex(prev => {
        const next = Math.min(prev + 1, filteredDocs.length - 1);
        virtuosoRef.current?.scrollIntoView({ index: next });
        return next;
      });
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setFocusedIndex(prev => {
        const next = Math.max(prev - 1, 0);
        virtuosoRef.current?.scrollIntoView({ index: next });
        return next;
      });
    } else if (e.key === 'Enter' && focusedIndex >= 0) {
      e.preventDefault();
      onSelect(filteredDocs[focusedIndex].filename);
    }
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case 'completed':
        return <Badge variant="success" className="gap-1"><CheckCircle className="w-3 h-3" />Ready</Badge>;
      case 'processing':
        return <Badge variant="processing" className="gap-1"><Clock className="w-3 h-3" />Processing</Badge>;
      case 'failed':
        return <Badge variant="destructive" className="gap-1"><XCircle className="w-3 h-3" />Failed</Badge>;
      default:
        return null;
    }
  };

  const Row = (index) => {
    const doc = filteredDocs[index];
    if (!doc) return null;

    const isCompleted = doc.status === 'completed';
    const isSelected = selectedDocs.includes(doc.filename);
    const isActive = activePdf === doc.filename;
    const isFocused = index === focusedIndex;

    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: index * 0.02 }}
        className="px-2"
      >
        <Card
          className={cn(
            "p-3 transition-smooth cursor-pointer hover:border-primary/50",
            isActive && "border-primary bg-primary/5",
            isFocused && "ring-2 ring-primary"
          )}
          onClick={() => isCompleted && onSelect(doc.filename)}
        >
          <div className="flex items-start gap-3">
            <button
              onClick={(e) => {
                e.stopPropagation();
                isCompleted && onToggleSelection(doc.filename);
              }}
              disabled={!isCompleted}
              className={cn(
                "w-5 h-5 rounded border-2 flex items-center justify-center transition-smooth mt-0.5",
                isSelected 
                  ? "bg-primary border-primary" 
                  : "border-muted-foreground hover:border-primary",
                !isCompleted && "opacity-50 cursor-not-allowed"
              )}
            >
              {isSelected && <CheckCircle className="w-3 h-3 text-white" />}
            </button>

            <div className={cn(
              "w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0",
              isActive ? "bg-primary/20" : "bg-muted"
            )}>
              <FileText className={cn("w-5 h-5", isActive ? "text-primary" : "text-muted-foreground")} />
            </div>

            <div className="flex-1 min-w-0">
              <div className="flex items-start justify-between gap-2 mb-1">
                <p 
                  className={cn(
                    "text-sm font-medium truncate",
                    isActive ? "text-primary" : "text-foreground"
                  )}
                  dangerouslySetInnerHTML={{
                    __html: searchTerm
                      ? doc.filename.replace(
                          new RegExp(`(${searchTerm})`, 'gi'),
                          '<span class="bg-primary/20 text-primary font-semibold">$1</span>'
                        )
                      : doc.filename
                  }}
                />
                {getStatusBadge(doc.status)}
              </div>
              
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                {doc.size && <span>{(doc.size / 1024).toFixed(1)} KB</span>}
                {doc.searchScore !== undefined && searchTerm && (
                  <>
                    <span>·</span>
                    <span>Match: {Math.round(doc.searchScore)}</span>
                  </>
                )}
              </div>
            </div>

            {isCompleted && (
              <div className="flex items-center gap-1">
                <SummarizeButton
                  filename={doc.filename}
                  onSummaryReceived={onSummaryReceived}
                  isIconOnly={true}
                />
                
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 text-muted-foreground hover:text-primary"
                  onClick={(e) => {
                    e.stopPropagation();
                    onSelect(doc.filename);
                  }}
                >
                  <Eye className="w-4 h-4" />
                </Button>

                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 text-muted-foreground hover:text-destructive"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(doc.filename);
                  }}
                >
                  <Trash2 className="w-4 h-4" />
                </Button>
              </div>
            )}
          </div>
        </Card>
      </motion.div>
    );
  };

  return (
    <div className="flex flex-col h-full">
      <div className="p-4 space-y-3">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            type="text"
            placeholder="Search documents..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            onKeyDown={handleKeyDown}
            className="pl-9"
          />
        </div>

        {selectedDocs.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex items-center justify-between text-sm"
          >
            <span className="text-muted-foreground">
              {selectedDocs.length} selected
            </span>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => selectedDocs.forEach(filename => onToggleSelection(filename))}
            >
              Clear selection
            </Button>
          </motion.div>
        )}
      </div>

      <Separator />

      <div className="flex-1 overflow-hidden">
        {filteredDocs.length === 0 ? (
          <div className="flex items-center justify-center h-full text-center p-4">
            <div>
              <FileText className="w-12 h-12 text-muted-foreground mx-auto mb-3" />
              <p className="text-sm text-muted-foreground">
                {searchTerm ? 'No documents match your search' : 'No documents yet'}
              </p>
            </div>
          </div>
        ) : (
          <Virtuoso
            ref={virtuosoRef}
            data={filteredDocs}
            itemContent={(index) => Row(index)}
            className="h-full"
            style={{ height: '100%' }}
          />
        )}
      </div>
    </div>
  );
}

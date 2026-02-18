import { useState } from 'react';
import { Trash2, FileText, PanelLeftClose, PanelLeft } from 'lucide-react';
import { useChatContext } from '@/contexts/ChatContext';
import { useDocumentContext } from '@/contexts/DocumentContext';
import { ChatInterface } from '@/components/chat/ChatInterface';
import { ChatInput } from '@/components/chat/ChatInput';
import { DocumentSelector } from '@/components/documents/DocumentSelector';
import { Button } from '@/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/ui/dialog';
import { AnimatePresence } from 'framer-motion';

const API_BASE_URL = 'http://127.0.0.1:8000';

export function ChatPage() {
  const { selectedDocs, handleDelete } = useDocumentContext();
  const { messages, isLoading, sendMessage, clearChat } = useChatContext();
  const [showClearDialog, setShowClearDialog] = useState(false);
  
  // FIX: Store the full source object { filename, page } or just the url suffix
  const [pdfPreviewState, setPdfPreviewState] = useState(null); // { filename, page }
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  const handleSend = (message) => {
    if (selectedDocs.length === 0) {
      alert('Please select at least one document first');
      return;
    }
    sendMessage(message, selectedDocs);
  };

  const handleExampleClick = (question) => {
    if (selectedDocs.length === 0) {
      alert('Please select at least one document first');
      return;
    }
    sendMessage(question, selectedDocs);
  };

  // Sidebar "View" click (No page number)
  const handleViewDocument = (filename) => {
    setPdfPreviewState({ filename, page: 1 });
  };

  // Chat Citation click (Has page number)
  const handleSourceClick = (source) => {
    // FIX: Parse the page number correctly
    const [filename, page] = source.split(':');
    setPdfPreviewState({ 
      filename, 
      page: page ? parseInt(page) : 1 
    });
  };

  const handleClearChat = () => {
    clearChat();
    setShowClearDialog(false);
  };

  return (
    <div className="h-full flex overflow-hidden">
      {/* Left Sidebar */}
      <AnimatePresence mode="wait">
        {isSidebarOpen && (
          <div className="h-full">
            <DocumentSelector 
              isOpen={true}
              onClose={() => setIsSidebarOpen(false)}
              compact={false}
              onView={handleViewDocument}
              onDelete={handleDelete}
            />
          </div>
        )}
      </AnimatePresence>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col bg-background h-full min-w-0">
        <div className="h-16 border-b border-border flex items-center justify-between px-6 flex-shrink-0">
          <div className="flex items-center gap-3">
            {!isSidebarOpen && (
              <Button variant="ghost" size="sm" onClick={() => setIsSidebarOpen(true)}>
                <PanelLeft className="w-4 h-4" />
              </Button>
            )}
            <h1 className="text-xl font-bold text-foreground">Chat</h1>
            {selectedDocs.length > 0 && (
              <div className="hidden md:block text-sm text-muted-foreground truncate max-w-[300px]">
                Chatting with: {selectedDocs.slice(0, 2).join(', ')}
                {selectedDocs.length > 2 && ` +${selectedDocs.length - 2} more`}
              </div>
            )}
          </div>
          {messages.length > 0 && (
            <Button variant="outline" size="sm" onClick={() => setShowClearDialog(true)}>
              <Trash2 className="w-4 h-4 mr-2" />
              Clear Chat
            </Button>
          )}
        </div>

        <div className="flex-1 overflow-hidden relative min-h-0">
          <ChatInterface
            messages={messages}
            isLoading={isLoading}
            onExampleClick={handleExampleClick}
            onSourceClick={handleSourceClick}
            /* FIX: Pass the full selectedDocs array, not just count, for smart suggestions */
            selectedDocs={selectedDocs}
          />
        </div>

        <div className="border-t border-border p-4 bg-background flex-shrink-0">
          <ChatInput
            onSend={handleSend}
            disabled={isLoading || selectedDocs.length === 0}
            placeholder={selectedDocs.length === 0 ? 'Select documents to start...' : 'Ask a question...'}
          />
        </div>
      </div>

      <Dialog open={showClearDialog} onOpenChange={setShowClearDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Clear Chat History?</DialogTitle>
            <DialogDescription>This will permanently delete all messages.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowClearDialog(false)}>Cancel</Button>
            <Button variant="destructive" onClick={handleClearChat}>Clear Chat</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* PDF Preview Dialog */}
      {pdfPreviewState && (
        <Dialog open={!!pdfPreviewState} onOpenChange={() => setPdfPreviewState(null)}>
          <DialogContent className="max-w-4xl h-[80vh] flex flex-col p-0 gap-0 overflow-hidden">
            <DialogHeader className="p-4 border-b border-border bg-card">
              <DialogTitle className="flex items-center gap-2">
                <FileText className="w-5 h-5 text-primary" />
                {pdfPreviewState.filename} 
                <span className="text-muted-foreground text-sm font-normal ml-2">
                  (Page {pdfPreviewState.page})
                </span>
              </DialogTitle>
            </DialogHeader>
            <div className="flex-1 bg-muted">
              {/* FIX: Append #page=X to the URL so browser jumps to specific page */}
              <iframe
                src={`${API_BASE_URL}/uploads/${pdfPreviewState.filename}#page=${pdfPreviewState.page}`}
                className="w-full h-full"
                title={pdfPreviewState.filename}
              />
            </div>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
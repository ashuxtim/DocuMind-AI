import { useRef, useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Loader2, Brain, Search, FileText, PenTool } from 'lucide-react';
import { ChatMessage } from './ChatMessage';
import { ChatEmpty } from './ChatEmpty';

// --- Thinking Indicator Component ---
function ThinkingIndicator() {
  const [step, setStep] = useState(0);
  
  const steps = [
    { text: "Reading documents...", icon: FileText },
    { text: "Extracting relevant context...", icon: Search },
    { text: "Analyzing data...", icon: Brain },
    { text: "Generating response...", icon: PenTool },
  ];

  useEffect(() => {
    const interval = setInterval(() => {
      setStep((prev) => (prev < steps.length - 1 ? prev + 1 : prev));
    }, 1500);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex flex-col gap-3 px-4 py-2 max-w-[80%]">
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
          <Loader2 className="w-4 h-4 text-primary animate-spin" />
        </div>
        <div className="flex flex-col">
          <span className="text-sm font-medium text-foreground animate-pulse">
            {steps[step].text}
          </span>
          <div className="flex gap-1 mt-1">
            {steps.map((_, idx) => (
              <div 
                key={idx} 
                className={`h-1 rounded-full transition-all duration-300 ${
                  idx <= step ? "w-4 bg-primary" : "w-1 bg-muted"
                }`} 
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export function ChatInterface({ 
  messages, 
  isLoading, 
  onSourceClick,
  onExampleClick,
  selectedDocs 
}) {
  const bottomRef = useRef(null);

  // Auto-scroll logic
  useEffect(() => {
    if (messages.length > 0 || isLoading) {
      // Small timeout ensures DOM is ready before scrolling
      setTimeout(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
      }, 100);
    }
  }, [messages, isLoading]);

  if (messages.length === 0 && !isLoading) {
    return (
      <ChatEmpty 
        onQuestionClick={onExampleClick}
        selectedDocs={selectedDocs}
      />
    );
  }

  return (
    // FIX: Changed 'flex-1' to 'h-full w-full' to ensure scrolling works
    <div className="h-full w-full overflow-y-auto p-4 space-y-6">
      {messages.map((message, index) => (
        <ChatMessage
          key={message.id || index}
          message={message}
          onSourceClick={onSourceClick}
          isLast={index === messages.length - 1} 
        />
      ))}
      
      {isLoading && (
        <motion.div 
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="pt-2"
        >
          <ThinkingIndicator />
        </motion.div>
      )}

      {/* Spacer div to ensure we can scroll to the very bottom */}
      <div ref={bottomRef} className="h-4" />
    </div>
  );
}
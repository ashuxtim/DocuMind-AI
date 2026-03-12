import { useState, useRef, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Send, Loader2 } from 'lucide-react';
import { Input } from '@/ui/input';
import { Button } from '@/ui/button';
import { cn } from '@/lib/utils';

export function ChatInput({ onSend, isLoading, disabled, placeholder }) {
  const [message, setMessage] = useState('');
  const inputRef = useRef(null);

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (message.trim() && !isLoading && !disabled) {
      onSend(message);
      setMessage('');
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <motion.form
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      onSubmit={handleSubmit}
      /* FIX: Removed p-4, border-t, and bg-card. 
         ChatPage.jsx already provides the sticky footer container. */
      className="w-full"
    >
      <div className="flex gap-2 max-w-4xl mx-auto">
        <div className="flex-1 relative">
          <Input
            ref={inputRef}
            type="text"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder || "Ask anything about your documents..."}
            disabled={disabled || isLoading}
            className="pr-12"
          />
          {message && (
            <motion.div
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              className="absolute right-3 top-1/2 -translate-y-1/2"
            >
              <span className="text-xs text-muted-foreground">
                {message.length}
              </span>
            </motion.div>
          )}
        </div>

        <Button
          type="submit"
          disabled={!message.trim() || isLoading || disabled}
          className={cn(
            "gap-2 min-w-[100px]",
            isLoading && "cursor-wait"
          )}
        >
          {isLoading ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Thinking...
            </>
          ) : (
            <>
              <Send className="w-4 h-4" />
              Send
            </>
          )}
        </Button>
      </div>

      {/* Hint Text */}
      <p className="text-xs text-muted-foreground text-center mt-2">
        Press Enter to send · Shift+Enter for new line
      </p>
    </motion.form>
  );
}
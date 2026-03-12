import { memo, useMemo, useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { User, Bot, CheckCircle2, TrendingUp, Lightbulb } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Card } from '@/ui/card';
import { cn } from '@/lib/utils';
import { SourceCitation } from './SourceCitation';

// --- GLOBAL MEMORY FOR ANIMATIONS ---
// This prevents animations from re-playing when you switch tabs
const typedMessageIds = new Set();

const ConfidenceMeter = ({ score }) => {
  const validScore = Math.max(0, Math.min(1, score || 0));
  const percentage = Math.round(validScore * 100);
  
  let colorClass = "text-red-500";
  if (validScore > 0.7) colorClass = "text-green-500";
  else if (validScore > 0.3) colorClass = "text-yellow-500";

  const radius = 14;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (validScore * circumference);

  return (
    <div className="flex items-center gap-2 mt-2 pt-2 border-t border-border/40 w-full">
      <div className="relative w-9 h-9 flex items-center justify-center flex-shrink-0">
        <svg className="w-full h-full transform -rotate-90">
          <circle cx="18" cy="18" r={radius} stroke="currentColor" strokeWidth="3" fill="transparent" className="text-muted/20" />
          <circle
            cx="18" cy="18" r={radius} stroke="currentColor" strokeWidth="3" fill="transparent"
            strokeDasharray={circumference} strokeDashoffset={strokeDashoffset} strokeLinecap="round"
            className={cn("transition-all duration-1000 ease-out", colorClass)}
          />
        </svg>
        <span className="absolute text-[9px] font-bold text-muted-foreground">{percentage}%</span>
      </div>
      <div className="flex flex-col">
        <span className="text-xs font-semibold text-foreground">Confidence Score</span>
        <span className="text-[10px] text-muted-foreground">Relevance match</span>
      </div>
    </div>
  );
};

// --- UPDATED HOOK: Handles persistence ---
const useTypewriter = (text, speed = 10, isEnabled = false, messageId) => {
  const [displayedText, setDisplayedText] = useState(isEnabled ? '' : text);
  const [isTyping, setIsTyping] = useState(isEnabled);

  useEffect(() => {
    // If disabled or text empty, show full immediately
    if (!isEnabled || !text) {
      setDisplayedText(text);
      setIsTyping(false);
      return;
    }

    // START TYPING
    setDisplayedText('');
    setIsTyping(true);

    let i = 0;
    const timer = setInterval(() => {
      if (i < text.length) {
        setDisplayedText((prev) => prev + text.charAt(i));
        i++;
      } else {
        clearInterval(timer);
        setIsTyping(false);
        // MARK AS DONE GLOBALLY
        if (messageId) typedMessageIds.add(messageId);
      }
    }, speed);

    return () => clearInterval(timer);
  }, [text, speed, isEnabled, messageId]);

  return { displayedText, isTyping };
};

export const ChatMessage = memo(({ message, onSourceClick, isLast }) => {
  const isUser = message.role === 'user';
  const isError = message.isError;

  // 1. SMART PRE-PROCESSING
  const processedContent = useMemo(() => {
    if (isUser || !message.content) return message.content;
    let text = message.content;
    const highlightKeywords = ['Conclusion', 'Key Takeaways', 'Summary', 'Recommendation'];
    
    highlightKeywords.forEach(keyword => {
      const regex = new RegExp(`(#{1,3}\\s*${keyword}[\\s\\S]*?)(?=\\n#{1,3}|$)`, 'gi');
      text = text.replace(regex, (match) => {
        return match.split('\n').map(line => `> ${line}`).join('\n');
      });
    });
    return text;
  }, [message.content, isUser]);

  // 2. ANIMATION LOGIC (FIXED)
  const isFresh = (new Date() - new Date(message.timestamp)) < 60000;
  // Check if we already typed this message ID
  const alreadyTyped = typedMessageIds.has(message.id);
  
  const shouldAnimate = !isUser && !isError && isLast && isFresh && !alreadyTyped;
  
  const { displayedText, isTyping } = useTypewriter(processedContent, 10, shouldAnimate, message.id);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className={cn(
        "flex gap-3 px-4 py-3",
        isUser ? "justify-end" : "justify-start"
      )}
    >
      {!isUser && (
        <div className={cn(
          "flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center mt-1",
          isError ? "bg-destructive/10 text-destructive" : "bg-primary/20"
        )}>
          <Bot className={cn("w-5 h-5", !isError && "text-primary")} />
        </div>
      )}

      <div className={cn("flex flex-col gap-2 max-w-[85%]", isUser ? "items-end" : "items-start")}>
        <Card
          className={cn(
            "p-5 shadow-sm transition-all duration-200",
            isUser ? "bg-primary text-primary-foreground border-primary" : "bg-card border-border",
            isError && "border-destructive/50 bg-destructive/5"
          )}
        >
          {isUser ? (
            <p className="text-sm whitespace-pre-wrap leading-relaxed">{message.content}</p>
          ) : (
            <div className="prose prose-slate dark:prose-invert max-w-none text-sm">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  h1: ({children}) => <h1 className="text-xl font-bold border-b border-border pb-2 mb-3 mt-4">{children}</h1>,
                  h2: ({children}) => (
                    <h2 className="text-base font-bold text-foreground mt-5 mb-2 flex items-center gap-2">
                      <span className="w-1 h-5 bg-primary rounded-full shrink-0"/>
                      {children}
                    </h2>
                  ),
                  h3: ({children}) => (
                    <h3 className="text-sm font-bold text-foreground/90 mt-4 mb-1 flex items-center gap-2">
                       <TrendingUp className="w-3.5 h-3.5 text-muted-foreground" />
                       {children}
                    </h3>
                  ),
                  blockquote: ({children}) => (
                    <div className="my-4 rounded-lg border border-primary/20 bg-primary/5 p-4 relative overflow-hidden group">
                      <Lightbulb className="absolute right-[-5px] top-[-5px] w-16 h-16 text-primary/5 rotate-12 transition-transform group-hover:rotate-0" />
                      <div className="relative z-10 [&>h1]:text-primary [&>h2]:text-primary [&>h3]:text-primary">
                        {children}
                      </div>
                    </div>
                  ),
                  ul: ({children}) => <ul className="my-3 space-y-2">{children}</ul>,
                  li: ({children}) => (
                    <li className="flex items-start gap-2.5 text-foreground/90 leading-relaxed">
                      <CheckCircle2 className="w-4 h-4 text-primary/60 mt-0.5 shrink-0" />
                      <span>{children}</span>
                    </li>
                  ),
                  code: ({ inline, children }) => 
                    inline ? (
                      <code className="px-1.5 py-0.5 rounded bg-muted text-primary text-xs font-mono font-medium border border-border">
                        {children}
                      </code>
                    ) : (
                      <code className="block p-3 rounded bg-muted text-xs font-mono overflow-x-auto my-2 border border-border">
                        {children}
                      </code>
                    ),
                  p: ({children}) => <p className="mb-3 last:mb-0 leading-relaxed text-muted-foreground">{children}</p>,
                }}
              >
                {displayedText + (isTyping ? " ▍" : "")}
              </ReactMarkdown>
            </div>
          )}

          {!isUser && !isError && !isTyping && (
            <motion.div 
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.2 }}
              className="flex flex-col gap-2 mt-4"
            >
              {message.sources?.length > 0 && (
                <div className="flex flex-wrap gap-1 mb-1">
                  {message.sources.map((source, idx) => (
                    <SourceCitation
                      key={idx}
                      source={source}
                      onClick={() => onSourceClick?.(source)}
                    />
                  ))}
                </div>
              )}
              
              {message.confidence !== undefined && (
                <ConfidenceMeter score={message.confidence} />
              )}
            </motion.div>
          )}
        </Card>
      </div>

      {isUser && (
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-secondary/20 flex items-center justify-center mt-1">
          <User className="w-5 h-5 text-secondary" />
        </div>
      )}
    </motion.div>
  );
});

ChatMessage.displayName = 'ChatMessage';
import { useState, useEffect, useMemo } from 'react';
import { motion } from 'framer-motion';
import { FileText, Calendar, Eye, CheckCircle2, TrendingUp, Lightbulb } from 'lucide-react';
import { Card, CardContent } from '@/ui/card';
import { Button } from '@/ui/button';
import { Badge } from '@/ui/badge';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

// --- GLOBAL MEMORY FOR SUMMARIES ---
const shownSummaries = new Set();

const useTypewriter = (text, speed = 8, isEnabled = false, filename) => {
  const [displayedText, setDisplayedText] = useState(isEnabled ? '' : text);
  const [isTyping, setIsTyping] = useState(isEnabled);

  useEffect(() => {
    if (!isEnabled || !text) {
      setDisplayedText(text || '');
      setIsTyping(false);
      return;
    }

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
        // Mark as shown so we don't animate again
        if (filename) shownSummaries.add(filename);
      }
    }, speed);

    return () => clearInterval(timer);
  }, [text, speed, isEnabled, filename]);

  return { displayedText, isTyping };
};

export function SummaryCard({ filename, summary, onViewDocument, createdAt, fileType }) {
  const isFresh = createdAt ? (new Date() - new Date(createdAt)) < 60000 : false;
  const alreadyShown = shownSummaries.has(filename);
  
  const processedSummary = useMemo(() => {
    if (!summary) return '';
    let text = summary;
    const highlightKeywords = ['Executive Summary', 'Key Takeaways', 'Conclusion', 'Strategic Highlights'];
    
    highlightKeywords.forEach(keyword => {
      const regex = new RegExp(`(#{1,3}\\s*${keyword}[\\s\\S]*?)(?=\\n#{1,3}|$)`, 'gi');
      text = text.replace(regex, (match) => {
        return match.split('\n').map(line => `> ${line}`).join('\n');
      });
    });

    return text;
  }, [summary]);

  // Only animate if it's fresh AND hasn't been shown yet
  const { displayedText, isTyping } = useTypewriter(
    processedSummary, 
    5, 
    isFresh && !alreadyShown, 
    filename
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="w-full"
    >
      <Card className="overflow-hidden shadow-sm border-border/60 bg-card hover:shadow-md transition-shadow duration-300">
        {/* Header */}
        <div className="border-b border-border bg-muted/10 p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-start gap-4">
            <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0 border border-primary/20">
              <FileText className="w-5 h-5 text-primary" />
            </div>
            <div>
              <h3 className="text-lg font-bold text-foreground tracking-tight">{filename}</h3>
              <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground font-medium">
                {createdAt && (
                  <span className="flex items-center gap-1.5">
                    <Calendar className="w-3.5 h-3.5" />
                    {new Date(createdAt).toLocaleDateString()}
                  </span>
                )}
                {fileType && (
                  <Badge variant="secondary" className="text-[10px] px-2 h-5 font-semibold uppercase">
                    {fileType}
                  </Badge>
                )}
              </div>
            </div>
          </div>

          <Button
            variant="ghost"
            size="sm"
            onClick={() => onViewDocument?.(filename)}
            className="flex-shrink-0 gap-2 text-muted-foreground hover:text-primary hover:bg-primary/5"
          >
            <Eye className="w-4 h-4" />
            View Original
          </Button>
        </div>

        {/* Content */}
        <CardContent className="p-8">
          <div className="prose prose-slate dark:prose-invert max-w-none">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                h1: ({children}) => (
                  <h1 className="text-2xl font-bold text-foreground border-b border-border pb-3 mb-6 mt-2 tracking-tight">
                    {children}
                  </h1>
                ),
                h2: ({children}) => (
                  <h2 className="text-lg font-semibold text-foreground mt-8 mb-4 flex items-center gap-3 pl-0">
                    <span className="w-1.5 h-6 bg-primary rounded-full shrink-0"></span>
                    {children}
                  </h2>
                ),
                h3: ({children}) => (
                  <h3 className="text-base font-semibold text-foreground/80 mt-6 mb-2 flex items-center gap-2">
                     <TrendingUp className="w-4 h-4 text-muted-foreground" />
                     {children}
                  </h3>
                ),
                blockquote: ({children}) => (
                  <div className="my-6 rounded-xl border border-primary/20 bg-primary/5 p-5 relative overflow-hidden">
                    <Lightbulb className="absolute right-[-10px] top-[-10px] w-24 h-24 text-primary/5 rotate-12 pointer-events-none" />
                    <div className="relative z-10 text-foreground/90 [&>h1]:border-0 [&>h1]:pb-0 [&>h1]:mb-2 [&>h1]:text-primary [&>h2]:border-0 [&>h2]:pl-0 [&>h2]:text-primary">
                      {children}
                    </div>
                  </div>
                ),
                ul: ({children}) => <ul className="my-4 space-y-2">{children}</ul>,
                li: ({children}) => (
                  <li className="flex items-start gap-3 text-foreground/80 leading-relaxed">
                    <CheckCircle2 className="w-4 h-4 text-green-500 mt-1 shrink-0" />
                    <span>{children}</span>
                  </li>
                ),
                p: ({children}) => <p className="leading-7 mb-4 text-muted-foreground">{children}</p>,
                strong: ({children}) => <span className="font-semibold text-foreground">{children}</span>,
                code: ({children}) => (
                  <span className="px-1.5 py-0.5 rounded-md bg-muted font-mono text-xs text-primary font-medium border border-border">
                    {children}
                  </span>
                ),
              }}
            >
              {displayedText + (isTyping ? " ▍" : "")}
            </ReactMarkdown>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}
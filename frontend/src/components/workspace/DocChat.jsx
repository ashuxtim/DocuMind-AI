import { useState, useEffect, useRef, useCallback } from 'react';
import { Sparkles, Loader2, Send, FileText } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useWorkspace } from '@/contexts/WorkspaceContext';

/**
 * DocChat — Right panel of Screen 2.
 * Shows auto-generated summary, suggested questions, chat messages,
 * and an input area. All state comes from WorkspaceContext.
 */
export default function DocChat() {
  const {
    activeDoc,
    messages,
    chatLoading,
    sendMessage,
    getSummary,
    isSummaryLoading,
    pdfViewerRef,
  } = useWorkspace();

  // ── Local state ──
  const [inputValue, setInputValue] = useState('');
  const bottomRef = useRef(null);
  const textareaRef = useRef(null);

  // ── Auto-scroll on new messages ──
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, chatLoading]);

  // ── Handlers ──
  const handleSend = useCallback(() => {
    if (!inputValue.trim() || chatLoading) return;
    sendMessage(inputValue.trim());
    setInputValue('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  }, [inputValue, chatLoading, sendMessage]);

  const handleKeyDown = useCallback(
    (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  const summary = getSummary(activeDoc);

  // ── Render ──
  return (
    <div className="flex-1 flex flex-col h-full bg-background min-w-0">
      {/* ── Scrollable message area ── */}
      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
        {/* Summary — loading state */}
        {isSummaryLoading(activeDoc) && !summary && (
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center flex-shrink-0">
              <Sparkles className="w-4 h-4 text-primary" />
            </div>
            <div className="flex-1 bg-muted rounded-xl rounded-tl-none p-4">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="w-4 h-4 animate-spin" />
                Generating summary…
              </div>
            </div>
          </div>
        )}

        {/* Summary — error state */}
        {summary && summary.error && (
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-full bg-destructive/20 flex items-center justify-center flex-shrink-0">
              <Sparkles className="w-4 h-4 text-destructive" />
            </div>
            <div className="flex-1 bg-muted rounded-xl rounded-tl-none p-4">
              <p className="text-sm text-destructive">
                {summary.message || 'Summary generation failed'}
              </p>
            </div>
          </div>
        )}

        {/* Summary — content */}
        {summary && summary.content && (
          <div className="flex items-start gap-3 mb-4">
            <div className="w-8 h-8 rounded-full bg-green-500/20 flex items-center justify-center flex-shrink-0">
              <Sparkles className="w-4 h-4 text-green-400" />
            </div>
            <div className="flex-1 bg-emerald-950/40 border-l-2 border-green-500 rounded-lg p-4">
              <p className="text-xs font-semibold text-green-400 mb-2 uppercase tracking-widest">
                Summary
              </p>
              <div className="prose prose-sm prose-invert max-w-none text-sm prose-headings:text-green-300 prose-p:text-slate-300 prose-strong:text-green-200 prose-li:text-slate-300">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {summary.content}
                </ReactMarkdown>
              </div>
            </div>
          </div>
        )}

        {/* Suggested questions — only when no messages yet */}
        {messages.length === 0 && summary && summary.content && (
          <div className="flex flex-wrap gap-2 pl-11 mt-1">
            {[
              'What are the key findings?',
              'What are the main risks?',
              'Summarize the recommendations',
            ].map((q) => (
              <button
                key={q}
                onClick={() => sendMessage(q)}
                className="bg-green-950/40 border border-green-700/50 text-green-300 text-xs rounded-full px-3 py-1.5 hover:bg-green-900/50 hover:border-green-500/60 transition-colors"
              >
                {q}
              </button>
            ))}
          </div>
        )}

        {/* Chat messages */}
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex items-start gap-3 mb-4 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
          >
            {/* Avatar */}
            {msg.role === 'user' ? (
              <div className="w-7 h-7 rounded-full bg-green-600 flex items-center justify-center flex-shrink-0 text-[10px] font-semibold text-white">
                You
              </div>
            ) : (
              <div className="w-7 h-7 rounded-full bg-slate-700/60 flex items-center justify-center flex-shrink-0 text-[10px] font-semibold text-green-400">
                AI
              </div>
            )}

            {/* Bubble */}
            {msg.role === 'user' ? (
              <div className="max-w-[75%] bg-green-900 text-green-50 rounded-2xl rounded-br-sm px-4 py-2.5 text-sm leading-relaxed">
                {msg.content}
              </div>
            ) : (
              (() => {
                // Strip [Source: ...] from content and render separately as badge
                const sourceMatch = msg.content.match(/\[Source:\s*([^\]]+)\]/);
                const cleanContent = msg.content.replace(/\[Source:\s*[^\]]+\]/g, '').trim();

                // Derive label from reliable backend sources array first,
                // fall back to LLM prose match if sources array is empty
                const sources = msg.sources || [];
                const sourceLabel = sources.length > 0
                  ? sources[0].split(':Pg')[0]          // "filename.pdf:Pg7" → "filename.pdf"
                  : sourceMatch
                    ? sourceMatch[1].split(/[,|]/)[0].trim()
                    : null;

                // sourceFull still needed for page extraction in onClick
                const sourceFull = sourceMatch ? sourceMatch[1] : sources[0] || null;

                return (
                  <div className="max-w-[85%]">
                    <div className="prose prose-sm prose-invert max-w-none text-sm prose-headings:text-green-300 prose-headings:font-semibold prose-headings:text-sm prose-headings:mb-1 prose-p:text-slate-200 prose-p:leading-relaxed prose-p:mb-2 prose-li:text-slate-200 prose-li:mb-0.5 prose-strong:text-white prose-strong:font-medium prose-ul:my-1 prose-ol:my-1">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {cleanContent}
                      </ReactMarkdown>
                    </div>
                    {sourceLabel && (
                      <button
                        onClick={() => {
                          const sources = msg.sources || [];

                          // Step 1: try to parse page from the LLM's own citation text
                          // The LLM outputs [Source: filename, Page X] or [Source: filename | Pg X]
                          const pageFromCitation = parseInt(
                            sourceFull?.match(/(?:Page|Pg)\s*(\d+)/i)?.[1]
                          );

                          // Step 2: fallback — find the specific page entry in sources array
                          // by matching both filename AND page if citation parse failed
                          const pageFromSources = (() => {
                            if (!sources || sources.length === 0) return null;
                            const label = sourceLabel.toLowerCase().replace('.pdf', '');
                            const sorted = [...sources].sort((a, b) => {
                              const pa = parseInt(a.match(/:Pg(\d+)/)?.[1]) || 0;
                              const pb = parseInt(b.match(/:Pg(\d+)/)?.[1]) || 0;
                              return pa - pb;
                            });
                            const match = sorted.find(s => s.toLowerCase().includes(label));
                            return match ? parseInt(match.match(/:Pg(\d+)/)?.[1]) : null;
                          })();

                          const pageNum = pageFromCitation || pageFromSources;

                          if (pageNum && pdfViewerRef.current) {
                            pdfViewerRef.current.scrollToPage(pageNum);
                          }
                        }}
                        className="inline-flex items-center gap-1.5 mt-3 px-2.5 py-1 rounded-md text-xs font-medium cursor-pointer bg-green-950/50 border border-green-800/50 text-green-400 hover:bg-green-900/50 hover:border-green-600/50 transition-colors"
                      >
                        <FileText size={10} />
                        {sourceLabel}
                      </button>
                    )}
                  </div>
                );
              })()
            )}
          </div>
        ))}

        {/* Typing indicator */}
        {chatLoading && (
          <div className="flex items-start gap-3 mb-4">
            <div className="w-7 h-7 rounded-full bg-slate-700/60 flex items-center justify-center flex-shrink-0 text-[10px] font-semibold text-green-400">
              AI
            </div>
            <div className="flex gap-1 pt-2">
              <div className="w-1.5 h-1.5 rounded-full bg-green-400/60 animate-bounce [animation-delay:0ms]" />
              <div className="w-1.5 h-1.5 rounded-full bg-green-400/60 animate-bounce [animation-delay:150ms]" />
              <div className="w-1.5 h-1.5 rounded-full bg-green-400/60 animate-bounce [animation-delay:300ms]" />
            </div>
          </div>
        )}

        {/* Scroll anchor */}
        <div ref={bottomRef} />
      </div>

      {/* ── Input area ── */}
      <div className="border-t border-border bg-card flex-shrink-0">
        <div className="flex items-end gap-3 px-4 py-3">

          {/* Avatar */}
          <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center flex-shrink-0 mb-0.5">
            <span className="text-xs font-semibold text-primary">You</span>
          </div>

          {/* Input + send wrapper */}
          <div className="flex-1 flex items-end gap-2 bg-muted rounded-2xl px-4 py-3 focus-within:ring-1 focus-within:ring-primary/40 transition-all">
            <textarea
              ref={textareaRef}
              value={inputValue}
              onChange={(e) => {
                setInputValue(e.target.value);
                const el = textareaRef.current;
                if (el) {
                  el.style.height = 'auto';
                  el.style.height = `${el.scrollHeight}px`;
                }
              }}
              onKeyDown={handleKeyDown}
              placeholder="Ask anything about this document..."
              className="flex-1 resize-none bg-transparent text-sm text-foreground placeholder:text-muted-foreground border-0 focus:outline-none min-h-[44px] max-h-40 overflow-hidden leading-relaxed"
            />
            <button
              onClick={handleSend}
              disabled={chatLoading || !inputValue.trim()}
              className="w-8 h-8 rounded-xl bg-primary text-primary-foreground flex items-center justify-center hover:bg-primary/90 transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex-shrink-0 mb-0.5"
            >
              <Send className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        <p className="text-[11px] text-muted-foreground/50 text-center pb-2">
          Enter to send · Shift+Enter for new line
        </p>
      </div>
    </div>
  );
}

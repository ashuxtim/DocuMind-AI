import { useState } from 'react';
import { Sparkles, Loader2 } from 'lucide-react';
import { Button } from '@/ui/button';
import { summarizeDocument } from '@/lib/api';

export default function SummarizeButton({ filename, onSummaryReceived, isIconOnly = false }) {
  const [loading, setLoading] = useState(false);

  const handleSummarize = async () => {
    setLoading(true);
    try {
      const response = await summarizeDocument(filename);
      onSummaryReceived({
        role: 'assistant',
        content: `📄 **Executive Summary for ${filename}**\n\n${response.data.summary}`,
        sources: [`${filename}:1`],
      });
    } catch (error) {
      console.error('Summary failed', error);
      onSummaryReceived({
        role: 'assistant',
        content: '❌ **Summary Failed**\nThe backend could not process this file. Is it empty?',
      });
    } finally {
      setLoading(false);
    }
  };

  if (isIconOnly) {
    return (
      <Button
        variant="ghost"
        size="icon"
        onClick={(e) => {
          e.stopPropagation();
          handleSummarize();
        }}
        disabled={loading}
        className="h-8 w-8 text-muted-foreground hover:text-secondary"
        title="Generate AI Summary"
      >
        {loading ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <Sparkles className="w-4 h-4" />
        )}
      </Button>
    );
  }

  return (
    <Button
      onClick={handleSummarize}
      disabled={loading}
      variant="outline"
      className="gap-2"
    >
      {loading ? (
        <>
          <Loader2 className="w-4 h-4 animate-spin" />
          Summarizing...
        </>
      ) : (
        <>
          <Sparkles className="w-4 h-4" />
          Summarize Doc
        </>
      )}
    </Button>
  );
}

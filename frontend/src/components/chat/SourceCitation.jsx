import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { FileText, ExternalLink, Hash } from 'lucide-react';
import { cn } from '@/lib/utils';

export function SourceCitation({ source, onClick }) {
  const [filename, page] = source.split(':');
  const [isHovered, setIsHovered] = useState(false);

  return (
    <div 
      className="relative inline-block"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* The Citation Chip */}
      <motion.button
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
        onClick={() => onClick?.(source)}
        className={cn(
          "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full", // Rounded full for "Chip" look
          "bg-primary/10 hover:bg-primary/20 transition-colors",
          "text-xs font-medium text-primary",
          "border border-primary/20 cursor-pointer select-none",
          "mt-1 mr-1"
        )}
      >
        <Hash className="w-3 h-3 opacity-70" />
        <span className="truncate max-w-[150px]">{filename}</span>
        {page && (
          <span className="opacity-70 text-[10px] ml-0.5">p.{page}</span>
        )}
      </motion.button>

      {/* The Tooltip Popup */}
      <AnimatePresence>
        {isHovered && (
          <motion.div
            initial={{ opacity: 0, y: 10, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 5, scale: 0.95 }}
            transition={{ duration: 0.15 }}
            className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50 w-64"
          >
            <div className="bg-popover text-popover-foreground rounded-lg shadow-xl border border-border p-3 text-xs">
              <div className="flex items-center gap-2 mb-2 border-b border-border/50 pb-2">
                <FileText className="w-3 h-3 text-primary" />
                <span className="font-semibold truncate">{filename}</span>
              </div>
              
              {/* Note: This text is a placeholder until backend sends snippets */}
              <div className="text-muted-foreground italic bg-muted/50 p-2 rounded">
                "Click to view the source context on page {page}..."
              </div>
              
              <div className="mt-2 flex items-center justify-end text-[10px] text-primary gap-1">
                <span>Open PDF</span>
                <ExternalLink className="w-3 h-3" />
              </div>

              {/* Arrow */}
              <div className="absolute top-full left-1/2 -translate-x-1/2 -mt-1 border-4 border-transparent border-t-popover" />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
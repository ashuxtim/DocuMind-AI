import { useState, useEffect } from 'react';
import { CheckCircle2, Loader2 } from 'lucide-react';
import { useSimulatedProgress } from '@/hooks/useSimulatedProgress';
import { cn } from '@/lib/utils';
import { AnimatePresence, motion } from 'framer-motion';

export function FileProcessing({ status, filename }) {
  // Pass filename to hook for persistence
  const progress = useSimulatedProgress(status, filename);
  
  // Visibility Logic:
  // If status is processing, SHOW.
  // If status is completed, SHOW for 5 seconds, then HIDE.
  const [isVisible, setIsVisible] = useState(status === 'processing');

  useEffect(() => {
    if (status === 'processing') {
      setIsVisible(true);
    } else if (status === 'completed') {
      // Keep success message visible longer (5 seconds) so user sees it
      const timer = setTimeout(() => setIsVisible(false), 5000);
      return () => clearTimeout(timer);
    }
  }, [status]);

  if (!isVisible) return null;

  const isDone = status === 'completed' || progress === 100;

  return (
    <AnimatePresence>
      <motion.div 
        initial={{ opacity: 0, height: 0 }}
        animate={{ opacity: 1, height: 'auto' }}
        exit={{ opacity: 0, height: 0 }}
        className="w-full flex flex-col gap-2 mt-2"
      >
        {/* Label Row */}
        <div className="flex justify-between items-center text-[10px] uppercase tracking-wider font-bold">
          <span className={cn("flex items-center gap-1.5 transition-colors duration-300", 
            isDone ? "text-green-600 dark:text-green-400" : "text-primary/80"
          )}>
            {isDone ? (
              <>
                <CheckCircle2 className="w-3.5 h-3.5" />
                Done
              </>
            ) : (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                Processing...
              </>
            )}
          </span>
          <span className="text-muted-foreground font-mono">{progress}%</span>
        </div>

        {/* Modern Styled Progress Bar */}
        <div className="h-2 w-full bg-secondary/50 rounded-full overflow-hidden relative shadow-inner">
          <div 
            className={cn(
              "h-full transition-all duration-700 ease-out relative", 
              isDone ? "bg-green-500" : "bg-primary"
            )}
            style={{ width: `${progress}%` }}
          >
            {/* Animated Stripes Overlay (Only when processing) */}
            {!isDone && (
              <div className="absolute inset-0 w-full h-full animate-[shimmer_1s_linear_infinite] bg-[linear-gradient(45deg,rgba(255,255,255,0.15)_25%,transparent_25%,transparent_50%,rgba(255,255,255,0.15)_50%,rgba(255,255,255,0.15)_75%,transparent_75%,transparent)] bg-[length:1rem_1rem]" />
            )}
            
            {/* Glow effect at the tip */}
            {!isDone && (
              <div className="absolute right-0 top-0 bottom-0 w-2 bg-white/50 blur-[2px]" />
            )}
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
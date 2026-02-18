import { motion } from 'framer-motion';
import { Loader2, XCircle } from 'lucide-react';
import { Button } from '@/ui/button';
import { Badge } from '@/ui/badge';
import { cn } from '@/lib/utils';

export function ProcessingIndicator({ 
  filename, 
  progress = 0, 
  onCancel,
  status = 'processing' 
}) {
  const radius = 20;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (progress / 100) * circumference;

  if (status === 'processing') {
    return (
      <div className="flex items-center gap-3">
        {/* Circular Progress */}
        <div className="relative w-12 h-12 flex-shrink-0">
          <svg className="w-full h-full transform -rotate-90">
            {/* Background circle */}
            <circle
              cx="24"
              cy="24"
              r={radius}
              stroke="currentColor"
              strokeWidth="3"
              fill="none"
              className="text-muted"
            />
            {/* Progress circle */}
            <motion.circle
              cx="24"
              cy="24"
              r={radius}
              stroke="currentColor"
              strokeWidth="3"
              fill="none"
              strokeDasharray={circumference}
              strokeDashoffset={strokeDashoffset}
              strokeLinecap="round"
              className="text-primary"
              initial={{ strokeDashoffset: circumference }}
              animate={{ strokeDashoffset }}
              transition={{ duration: 0.5 }}
            />
          </svg>
          
          {/* Center percentage */}
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="text-xs font-semibold text-foreground">
              {Math.round(progress)}%
            </span>
          </div>
        </div>

        {/* File info */}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-foreground truncate">
            {filename}
          </p>
          <div className="flex items-center gap-2 mt-1">
            <Badge variant="processing" className="text-xs">
              <Loader2 className="w-3 h-3 mr-1 animate-spin" />
              Processing
            </Badge>
            <span className="text-xs text-muted-foreground">
              {progress < 30 ? 'Parsing document...' : 
               progress < 70 ? 'Extracting content...' : 
               'Finalizing...'}
            </span>
          </div>
        </div>

        {/* Cancel button */}
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onCancel?.(filename)}
          className="text-destructive hover:text-destructive hover:bg-destructive/10"
        >
          <XCircle className="w-4 h-4 mr-1" />
          Cancel
        </Button>
      </div>
    );
  }

  return null;
}

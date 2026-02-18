import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Filter, ChevronDown, CheckCircle, Clock, XCircle } from 'lucide-react';
import { Button } from '@/ui/button';
import { Badge } from '@/ui/badge';
import { cn } from '@/lib/utils';

const filterOptions = [
  { value: 'all', label: 'All Documents', icon: Filter },
  { value: 'completed', label: 'Completed', icon: CheckCircle },
  { value: 'processing', label: 'Processing', icon: Clock },
  { value: 'failed', label: 'Failed', icon: XCircle },
];

export function DocumentFilters({ activeFilter, onFilterChange, counts }) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="space-y-2">
      <Button
        variant="outline"
        size="sm"
        onClick={() => setIsOpen(!isOpen)}
        className="w-full justify-between"
      >
        <span className="flex items-center gap-2">
          <Filter className="w-4 h-4" />
          Filter
        </span>
        <motion.div
          animate={{ rotate: isOpen ? 180 : 0 }}
          transition={{ duration: 0.2 }}
        >
          <ChevronDown className="w-4 h-4" />
        </motion.div>
      </Button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="space-y-1 overflow-hidden"
          >
            {filterOptions.map((option) => {
              const Icon = option.icon;
              const isActive = activeFilter === option.value;
              const count = counts?.[option.value] || 0;

              return (
                <motion.button
                  key={option.value}
                  whileHover={{ x: 4 }}
                  onClick={() => onFilterChange(option.value)}
                  className={cn(
                    "w-full flex items-center justify-between px-3 py-2 rounded-md transition-smooth text-sm",
                    isActive
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:text-foreground hover:bg-muted"
                  )}
                >
                  <span className="flex items-center gap-2">
                    <Icon className="w-4 h-4" />
                    {option.label}
                  </span>
                  <Badge variant={isActive ? "default" : "outline"} className="text-xs">
                    {count}
                  </Badge>
                </motion.button>
              );
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

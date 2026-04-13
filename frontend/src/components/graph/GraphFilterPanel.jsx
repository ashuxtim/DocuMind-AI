import { motion } from 'framer-motion';
import { X } from 'lucide-react';

const ALL_TYPES = ['Person', 'Organization', 'Statute', 'Date', 'Document', 'Entity'];

const TYPE_COLORS = {
  Person: '#34D399',
  Organization: '#FBBF24',
  Statute: '#A78BFA',
  Date: '#22D3EE',
  Document: '#F472B6',
  Entity: '#94A3B8',
};

export function GraphFilterPanel({
  isOpen,
  onClose,
  activeTypes,
  onToggleType,
  onShowAll,
  onHideAll,
  typeCounts,
}) {
  return (
    <motion.div
      initial={false}
      animate={{ x: isOpen ? 0 : -220 }}
      transition={{ type: 'spring', damping: 30, stiffness: 300 }}
      className="absolute top-0 left-0 h-full z-20 flex flex-col"
      style={{ width: 220 }}
    >
      <div className="h-full flex flex-col bg-slate-900/95 backdrop-blur-sm border-r border-slate-700/50 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-3 py-2.5 border-b border-slate-700/50 flex-none">
          <span className="text-xs font-semibold text-slate-200 tracking-wide uppercase">
            Filter by Type
          </span>
          <button
            onClick={onClose}
            className="flex items-center justify-center w-5 h-5 rounded text-slate-400 hover:text-slate-200 hover:bg-slate-700/60 transition-colors"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Type rows */}
        <div className="flex-1 overflow-y-auto py-1">
          {ALL_TYPES.map((type) => {
            const active = activeTypes.has(type);
            const count = typeCounts[type] ?? 0;
            return (
              <button
                key={type}
                onClick={() => onToggleType(type)}
                className="w-full flex items-center gap-2.5 px-3 py-2 text-left transition-opacity hover:bg-slate-700/40"
                style={{ opacity: active ? 1 : 0.4 }}
              >
                {/* Colored dot */}
                <span
                  className="flex-none w-2.5 h-2.5 rounded-full"
                  style={{ backgroundColor: TYPE_COLORS[type] }}
                />
                {/* Type name */}
                <span className="flex-1 text-xs text-slate-200 font-medium">
                  {type}
                </span>
                {/* Count badge */}
                <span className="flex-none text-xs text-slate-400 tabular-nums">
                  {count.toLocaleString()}
                </span>
                {/* Active indicator */}
                <span
                  className="flex-none w-1.5 h-1.5 rounded-full transition-colors"
                  style={{ backgroundColor: active ? TYPE_COLORS[type] : 'transparent',
                           boxShadow: active ? `0 0 4px ${TYPE_COLORS[type]}` : 'none' }}
                />
              </button>
            );
          })}
        </div>

        {/* Divider + action buttons */}
        <div className="flex-none border-t border-slate-700/50 p-2.5 flex flex-col gap-1.5">
          <button
            onClick={onShowAll}
            className="w-full text-xs font-medium text-slate-200 py-1.5 px-3 rounded
                       bg-slate-700/60 hover:bg-slate-600/60 transition-colors text-center"
          >
            Show All
          </button>
          <button
            onClick={onHideAll}
            className="w-full text-xs font-medium text-slate-400 py-1.5 px-3 rounded
                       hover:bg-slate-700/40 hover:text-slate-200 transition-colors text-center"
          >
            Hide All
          </button>
        </div>
      </div>
    </motion.div>
  );
}

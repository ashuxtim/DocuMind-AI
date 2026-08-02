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
      animate={{ x: isOpen ? 0 : -260 }}
      transition={{ type: 'spring', damping: 30, stiffness: 300 }}
      className="absolute top-16 left-3 bottom-14 z-20 flex flex-col"
      style={{ width: 240 }}
    >
      <div className="h-full flex flex-col bg-[#101018]/95 backdrop-blur-md border border-[#2a2a3a] rounded-xl shadow-glass overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-3.5 py-3 border-b border-[#2a2a3a] flex-none">
          <span className="text-xs font-semibold text-[#e4e4ed] tracking-wider uppercase font-sans">
            Filter by Type
          </span>
          <button
            onClick={onClose}
            className="flex items-center justify-center w-6 h-6 rounded-lg text-[#8888a0] hover:text-[#e4e4ed] hover:bg-[#1c1c28] transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Type rows */}
        <div className="flex-1 overflow-y-auto py-1 scrollbar-thin">
          {ALL_TYPES.map((type) => {
            const active = activeTypes.has(type);
            const count = typeCounts[type] ?? 0;
            return (
              <button
                key={type}
                onClick={() => onToggleType(type)}
                className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-left transition-all hover:bg-[#1c1c28]"
                style={{ opacity: active ? 1 : 0.4 }}
              >
                {/* Colored dot */}
                <span
                  className="flex-none w-2.5 h-2.5 rounded-full shadow-sm"
                  style={{ backgroundColor: TYPE_COLORS[type] }}
                />
                {/* Type name */}
                <span className="flex-1 text-xs text-[#e4e4ed] font-sans font-medium">
                  {type}
                </span>
                {/* Count badge */}
                <span className="flex-none text-xs text-[#8888a0] font-mono tabular-nums">
                  {count.toLocaleString()}
                </span>
                {/* Active indicator */}
                <span
                  className="flex-none w-1.5 h-1.5 rounded-full transition-all"
                  style={{
                    backgroundColor: active ? TYPE_COLORS[type] : 'transparent',
                    boxShadow: active ? `0 0 6px ${TYPE_COLORS[type]}` : 'none',
                  }}
                />
              </button>
            );
          })}
        </div>

        {/* Action buttons */}
        <div className="flex-none border-t border-[#2a2a3a] p-3 flex flex-col gap-2 bg-[#0a0a10]/60">
          <button
            onClick={onShowAll}
            className="w-full text-xs font-sans font-medium text-[#e4e4ed] py-2 px-3 rounded-lg bg-[#16161f] border border-[#2a2a3a] hover:bg-[#1c1c28] hover:border-[#7c3aed]/50 transition-all text-center shadow-sm"
          >
            Show All
          </button>
          <button
            onClick={onHideAll}
            className="w-full text-xs font-sans font-medium text-[#8888a0] py-2 px-3 rounded-lg hover:bg-[#1c1c28] hover:text-[#e4e4ed] transition-all text-center"
          >
            Hide All
          </button>
        </div>
      </div>
    </motion.div>
  );
}


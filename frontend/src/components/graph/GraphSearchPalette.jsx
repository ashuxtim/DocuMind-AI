import { useState, useMemo, useRef, useEffect } from 'react';
import { Search } from 'lucide-react';
import { Input } from '@/ui/input';

const TYPE_COLORS = {
  Person: '#34D399',
  Organization: '#FBBF24',
  Statute: '#A78BFA',
  Date: '#22D3EE',
  Document: '#F472B6',
  Entity: '#94A3B8',
};

export function GraphSearchPalette({ graph, onSelectNode }) {
  const [query, setQuery] = useState('');
  const [isOpen, setIsOpen] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const containerRef = useRef(null);
  const inputRef = useRef(null);

  // Compute search matching results over graph nodes
  const results = useMemo(() => {
    if (!graph || !query.trim()) return [];

    const searchLower = query.toLowerCase();
    const matches = [];

    graph.forEachNode((nodeId, attrs) => {
      const label = attrs.label || nodeId;
      const group = attrs.group || 'Entity';
      if (label.toLowerCase().includes(searchLower)) {
        matches.push({
          id: nodeId,
          label: label,
          group: group,
          color: TYPE_COLORS[group] || '#94A3B8',
        });
      }
    });

    return matches.slice(0, 10);
  }, [graph, query]);

  // Click outside listener
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Cmd+K / Ctrl+K keyboard shortcut
  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        inputRef.current?.focus();
        setIsOpen(true);
      }
      if (e.key === 'Escape') {
        setIsOpen(false);
        inputRef.current?.blur();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, []);

  const handleKeyDown = (e) => {
    if (!isOpen || results.length === 0) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev + 1) % results.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev - 1 + results.length) % results.length);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const target = results[selectedIndex];
      if (target) {
        onSelectNode(target.id);
        setIsOpen(false);
      }
    }
  };

  return (
    <div ref={containerRef} className="relative flex items-center">
      <Search className="w-3.5 h-3.5 absolute left-2.5 text-[#5a5a70] pointer-events-none" />
      <Input
        ref={inputRef}
        className="h-8 w-44 sm:w-60 text-xs pl-8 pr-12 bg-[#0a0a10]/80 border-[#2a2a3a] text-[#e4e4ed] placeholder-[#5a5a70] focus:border-[#7c3aed] focus:ring-1 focus:ring-[#7c3aed] transition-all font-sans"
        placeholder="Search nodes (⌘K)..."
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setIsOpen(true);
          setSelectedIndex(0);
        }}
        onFocus={() => setIsOpen(true)}
        onKeyDown={handleKeyDown}
      />
      <kbd className="absolute right-2 px-1.5 py-0.5 text-[9px] font-mono text-[#5a5a70] bg-[#16161f] border border-[#2a2a3a] rounded pointer-events-none">
        ⌘K
      </kbd>

      {/* Autocomplete Dropdown */}
      {isOpen && results.length > 0 && (
        <div className="absolute top-full left-0 right-0 mt-1.5 bg-[#101018]/95 backdrop-blur-md border border-[#2a2a3a] rounded-xl shadow-glass overflow-hidden z-40 max-h-64 overflow-y-auto scrollbar-thin">
          <div className="p-1">
            {results.map((item, idx) => (
              <button
                key={item.id}
                onClick={() => {
                  onSelectNode(item.id);
                  setIsOpen(false);
                }}
                onMouseEnter={() => setSelectedIndex(idx)}
                className={`w-full flex items-center justify-between gap-2 px-3 py-2 text-left rounded-lg transition-all ${
                  idx === selectedIndex ? 'bg-[#1c1c28] border border-[#2a2a3a]' : 'hover:bg-[#16161f]'
                }`}
              >
                <span className="text-xs text-[#e4e4ed] font-sans font-medium truncate flex-1">
                  {item.label}
                </span>
                <span
                  className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded-full flex-none"
                  style={{
                    backgroundColor: `${item.color}22`,
                    color: item.color,
                    border: `1px solid ${item.color}44`,
                  }}
                >
                  {item.group}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

import { Search } from 'lucide-react';

/**
 * DocumentSearch — horizontal search + sort + count bar.
 *
 * Props:
 *   query         — current search string
 *   onQueryChange — (q: string) => void
 *   sortBy        — current sort key
 *   onSortChange  — (sort: string) => void
 *   totalCount    — total number of documents
 *   filteredCount — number of documents after filtering
 */
export default function DocumentSearch({
  query,
  onQueryChange,
  sortBy,
  onSortChange,
  totalCount,
  filteredCount,
}) {
  const hasQuery = query.trim().length > 0;

  return (
    <div className="flex items-center justify-between gap-4">
      {/* ── Search input ── */}
      <div className="relative w-64">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
        <input
          type="text"
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          placeholder="Search documents..."
          className="
            w-full pl-9 pr-3 py-2
            bg-muted border-0 rounded-lg
            text-sm text-foreground placeholder:text-muted-foreground
            outline-none focus:ring-2 focus:ring-ring
          "
        />
      </div>

      {/* ── Right side: sort + count ── */}
      <div className="flex items-center gap-2">
        <select
          value={sortBy}
          onChange={(e) => onSortChange(e.target.value)}
          className="
            bg-muted border-0 rounded-lg
            text-sm text-foreground
            px-3 py-2
            outline-none focus:ring-2 focus:ring-ring
            cursor-pointer
          "
        >
          <option value="date-desc">Newest first</option>
          <option value="date-asc">Oldest first</option>
          <option value="name-asc">Name A→Z</option>
          <option value="name-desc">Name Z→A</option>
          <option value="size-desc">Largest first</option>
        </select>

        <span className="text-sm text-muted-foreground whitespace-nowrap">
          {hasQuery
            ? `${filteredCount} of ${totalCount}`
            : `${totalCount} documents`}
        </span>
      </div>
    </div>
  );
}

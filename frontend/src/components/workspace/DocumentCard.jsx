import { useState } from 'react';
import { FileText, File, Eye, ExternalLink, Trash2 } from 'lucide-react';

/**
 * Derive file extension from filename.
 */
function getExt(filename) {
  const dot = filename.lastIndexOf('.');
  return dot === -1 ? '' : filename.slice(dot + 1).toLowerCase();
}

/**
 * Human-readable file size.
 */
function formatSize(bytes) {
  if (!bytes && bytes !== 0) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * Short date string.
 */
function formatDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

/**
 * Thumbnail style keyed by extension.
 */
function getFileStyle(ext) {
  switch (ext) {
    case 'pdf':
      return {
        Icon: FileText,
        bg: 'bg-gradient-to-br from-red-950 to-red-900',
        iconColor: 'text-red-400/60',
        initialsColor: 'text-red-400/10',
      };
    case 'doc':
    case 'docx':
      return {
        Icon: FileText,
        bg: 'bg-gradient-to-br from-blue-950 to-blue-900',
        iconColor: 'text-blue-400/60',
        initialsColor: 'text-blue-400/10',
      };
    default:
      return {
        Icon: File,
        bg: 'bg-gradient-to-br from-zinc-800 to-zinc-900',
        iconColor: 'text-zinc-400/60',
        initialsColor: 'text-zinc-400/10',
      };
  }
}

/**
 * Status badge colours.
 */
function statusBadge(status) {
  switch (status) {
    case 'completed':
      return { label: 'Ready', cls: 'bg-emerald-500/20 text-emerald-400' };
    case 'processing':
      return { label: 'Processing', cls: 'bg-amber-500/20 text-amber-400 animate-pulse' };
    case 'failed':
      return { label: 'Failed', cls: 'bg-red-500/20 text-red-400' };
    default:
      return { label: status || '…', cls: 'bg-muted text-muted-foreground' };
  }
}

/**
 * DocumentCard — YouTube-thumbnail-style card for a single document.
 *
 * Props:
 *   doc        — { filename, size, status, uploaded_at }
 *   isSelected — highlight ring when true
 *   onOpen     — (filename) => void
 *   onDelete   — (filename) => void
 *   onPreview  — (filename) => void
 */
export default function DocumentCard({ doc, isSelected, onOpen, onDelete, onPreview }) {
  const ext = getExt(doc.filename);
  const { Icon, bg, iconColor, initialsColor } = getFileStyle(ext);
  const badge = statusBadge(doc.status);
  const initials = doc.filename.slice(0, 2).toUpperCase();
  const [nameHovered, setNameHovered] = useState(false);

  return (
    <button
      type="button"
      onClick={() => onOpen(doc.filename)}
      className={`
        group relative flex flex-col w-full rounded-lg
        cursor-pointer transition-shadow duration-200
        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring
        ${isSelected ? 'ring-2 ring-primary' : 'hover:shadow-lg hover:shadow-black/20'}
      `}
    >
      {/* ── Delete button (top-left, visible on hover) ── */}
      <span
        role="button"
        tabIndex={0}
        onClick={(e) => { e.stopPropagation(); onDelete(doc.filename); }}
        onKeyDown={(e) => { if (e.key === 'Enter') { e.stopPropagation(); onDelete(doc.filename); } }}
        className="
          absolute top-2 left-2 z-20
          hidden group-hover:flex items-center justify-center
          w-6 h-6 rounded-full bg-destructive/80 text-white
          hover:bg-destructive transition-colors
        "
      >
        <Trash2 className="w-3.5 h-3.5" />
      </span>

      {/* ── Thumbnail area ── */}
      <div className={`relative overflow-hidden rounded-t-lg ${bg} aspect-[4/3]`}>
        {/* Faded initials — decorative background text */}
        <span className={`absolute top-1 left-2 text-7xl font-black leading-none select-none pointer-events-none ${initialsColor}`}>
          {initials}
        </span>

        {/* Centered icon */}
        <div className="absolute inset-0 flex items-center justify-center">
          <Icon className={`w-16 h-16 ${iconColor}`} strokeWidth={1.2} />
        </div>

        {/* Status badge */}
        <span className={`absolute top-2 right-2 text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full ${badge.cls}`}>
          {badge.label}
        </span>

        {/* Hover overlay */}
        <div className="
          absolute inset-0 rounded-t-lg bg-black/60
          opacity-0 group-hover:opacity-100 transition-opacity duration-200
          flex items-center justify-center gap-3
        ">
          <span
            role="button"
            tabIndex={0}
            onClick={(e) => { e.stopPropagation(); onPreview(doc.filename); }}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.stopPropagation(); onPreview(doc.filename); } }}
            className="flex items-center justify-center w-10 h-10 rounded-full hover:bg-white/20 transition-colors"
          >
            <Eye className="w-5 h-5 text-white" />
          </span>
          <span
            role="button"
            tabIndex={0}
            onClick={(e) => { e.stopPropagation(); onOpen(doc.filename); }}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.stopPropagation(); onOpen(doc.filename); } }}
            className="flex items-center justify-center w-10 h-10 rounded-full hover:bg-white/20 transition-colors"
          >
            <ExternalLink className="w-5 h-5 text-white" />
          </span>
        </div>
      </div>

      {/* ── Metadata area ── */}
      <div className="bg-card rounded-b-lg border border-border border-t-0 p-3 text-left">
        <div
          className="overflow-hidden"
          onMouseEnter={() => setNameHovered(true)}
          onMouseLeave={() => setNameHovered(false)}
        >
          <p
            className="text-sm font-medium text-foreground"
            style={{
              whiteSpace: 'nowrap',
              display: 'inline-block',
              transform: nameHovered ? 'translateX(-100%)' : 'translateX(0)',
              transition: nameHovered
                ? 'transform 4s linear'
                : 'transform 0.5s ease',
              paddingRight: '2rem',
            }}
          >
            {doc.filename}
          </p>
        </div>
        <div className="flex items-center gap-2 mt-1.5">
          <span className="text-[10px] uppercase bg-muted px-1.5 py-0.5 rounded font-semibold text-muted-foreground">
            {ext || '?'}
          </span>
          <span className="text-xs text-muted-foreground">{formatSize(doc.size)}</span>
          <span className="text-xs text-muted-foreground ml-auto">{formatDate(doc.uploaded_at)}</span>
        </div>
      </div>
    </button>
  );
}

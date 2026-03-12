// --- Graph Color Utilities ---
// Module-scope color map and color functions for graph rendering.
//
// Palette: muted jewel tones on dark background.
// Edges are visible but never compete with nodes.

export const NODE_COLOR_MAP = {
    Person: '#34D399',       // Emerald-400 (brighter than 500, reads better on black)
    Organization: '#FBBF24', // Amber-400
    Statute: '#A78BFA',      // Violet-400
    Date: '#22D3EE',         // Cyan-400
    Document: '#F472B6',     // Pink-400
    Entity: '#94A3B8',       // Slate-400
};

/**
 * Returns the color for a given node based on its group and hover state.
 */
export function getNodeColor(node, hoveredId, neighborIds) {
    if (hoveredId) {
        if (node.id === hoveredId) return '#10B981';
        if (neighborIds.has(node.id)) return '#6366F1';
        return 'rgba(100, 116, 139, 0.25)';
    }
    return NODE_COLOR_MAP[node.group] || NODE_COLOR_MAP.Entity;
}

/**
 * Returns the color for a link based on hover/highlight and type.
 * Base edges are subtle-but-visible; highlighted edges pop.
 */
export function getLinkColor(link, hoveredId, highlightLinks) {
    if (hoveredId) {
        return highlightLinks.has(link)
            ? 'rgba(129, 140, 248, 0.65)'       // indigo-400, clearly visible
            : 'rgba(100, 116, 139, 0.06)';      // nearly hidden
    }

    // Edge type differentiation
    const label = link.label || '';
    if (['CONTRADICTS', 'SUPERSEDES', 'NEGATES'].includes(label)) {
        return 'rgba(248, 113, 113, 0.30)';     // warm red-400, NOT neon
    }
    if (label === 'REVISES') {
        return 'rgba(251, 191, 36, 0.28)';      // amber-400
    }
    return 'rgba(148, 163, 184, 0.18)';          // slate-400, subtle but present
}

/**
 * Returns dash pattern for adversarial edge types.
 */
export function getLinkDash(link) {
    const label = link.label || '';
    if (['CONTRADICTS', 'SUPERSEDES', 'NEGATES', 'REVISES'].includes(label)) {
        return [5, 5];
    }
    return null;
}

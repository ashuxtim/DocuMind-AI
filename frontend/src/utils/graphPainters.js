// --- Graph Canvas Paint Functions ---
// Pure functions for Canvas 2D node/label rendering.
// No React dependencies — receives state as plain objects.
//
// Visual philosophy: Constellation-like. Quiet hubs glow softly,
// connections trace like starlines, labels appear only when relevant.
// Additive blending used sparingly (hovered + hubs only).

import { getNodeColor, NODE_COLOR_MAP } from './graphColors';

// ---------- helpers ----------

/** Hex (#RRGGBB) → { r, g, b } */
function hexToRgb(hex) {
    const n = parseInt(hex.slice(1), 16);
    return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}

/** Returns an rgba() string from a hex color + alpha (0-1). */
function rgba(hex, a) {
    const { r, g, b } = hexToRgb(hex);
    return `rgba(${r},${g},${b},${a})`;
}

/** Desaturate a hex color toward gray by `amount` (0 = original, 1 = gray). */
function desaturate(hex, amount) {
    const { r, g, b } = hexToRgb(hex);
    const gray = Math.round(r * 0.299 + g * 0.587 + b * 0.114);
    const mix = (c) => Math.round(c + (gray - c) * amount);
    return `rgb(${mix(r)},${mix(g)},${mix(b)})`;
}

// Degree classification thresholds
const HIGH_DEGREE = 8;
const MED_DEGREE = 3;

// ---------- main node painter ----------

/**
 * Main node paint function for react-force-graph-2d's nodeCanvasObject.
 *
 * @param {object} node
 * @param {CanvasRenderingContext2D} ctx
 * @param {number} globalScale
 * @param {object} state - { hoveredId, neighborIds, highlightLinks, tier, viewport }
 */
export function paintNode(node, ctx, globalScale, state) {
    // Guard: skip nodes with non-finite coordinates (during simulation warmup)
    if (!isFinite(node.x) || !isFinite(node.y)) return;

    const { hoveredId, neighborIds, tier, viewport } = state;
    const degree = node.connections || 1;

    // --- Degree-based sizing (log scale, no extreme jumps) ---
    const baseRadius = Math.max(3, Math.sqrt(node.val || 1) * 4);
    let nodeRadius;
    if (degree >= HIGH_DEGREE) {
        nodeRadius = baseRadius * 1.15;       // hubs slightly larger
    } else if (degree <= 1) {
        nodeRadius = baseRadius * 0.8;        // leaf nodes smaller
    } else {
        nodeRadius = baseRadius;
    }

    // --- Viewport culling: skip off-screen nodes ---
    if (viewport) {
        const margin = nodeRadius + 30;
        if (
            node.x < viewport.left - margin ||
            node.x > viewport.right + margin ||
            node.y < viewport.top - margin ||
            node.y > viewport.bottom + margin
        ) {
            return;
        }
    }

    const rawColor = NODE_COLOR_MAP[node.group] || NODE_COLOR_MAP.Entity;
    const isHovered = hoveredId && node.id === hoveredId;
    const isNeighbor = hoveredId && neighborIds.has(node.id);
    const isDimmed = hoveredId && !isHovered && !isNeighbor;

    // --- Degree-based saturation falloff for depth illusion ---
    let fillColor;
    if (isHovered) {
        fillColor = '#10B981';
    } else if (isNeighbor) {
        fillColor = '#6366F1';
    } else if (isDimmed) {
        fillColor = 'rgba(100,116,139,0.25)';
    } else if (degree <= 1) {
        fillColor = desaturate(rawColor, 0.45);  // leaves: noticeably desaturated
    } else if (degree < MED_DEGREE) {
        fillColor = desaturate(rawColor, 0.2);   // low: slightly muted
    } else {
        fillColor = rawColor;                     // medium+high: full color
    }

    // --- LOD: simple dot at very low zoom ---
    if (globalScale < 0.4 && !isHovered && !isNeighbor) {
        ctx.fillStyle = fillColor;
        ctx.beginPath();
        ctx.arc(node.x, node.y, Math.max(1.5, nodeRadius * 0.5), 0, 2 * Math.PI);
        ctx.fill();
        return;
    }

    const isHub = degree >= HIGH_DEGREE;

    // ====================================================================
    //  LAYER 1 — Shadow (single offset circle for depth)
    // ====================================================================
    if (!isDimmed) {
        ctx.fillStyle = 'rgba(0,0,0,0.35)';
        ctx.beginPath();
        ctx.arc(node.x + 1.5, node.y + 1.5, nodeRadius + 1, 0, 2 * Math.PI);
        ctx.fill();
    }

    // ====================================================================
    //  LAYER 2 — Core circle
    // ====================================================================
    ctx.fillStyle = fillColor;
    ctx.beginPath();
    ctx.arc(node.x, node.y, nodeRadius, 0, 2 * Math.PI);
    ctx.fill();

    // ====================================================================
    //  LAYER 3 — Border ring
    // ====================================================================
    if (isHovered) {
        ctx.strokeStyle = 'rgba(255,255,255,0.9)';
    } else if (isNeighbor) {
        ctx.strokeStyle = 'rgba(255,255,255,0.45)';
    } else if (isDimmed) {
        ctx.strokeStyle = 'rgba(255,255,255,0.06)';
    } else if (isHub) {
        ctx.strokeStyle = 'rgba(255,255,255,0.3)';
    } else {
        ctx.strokeStyle = 'rgba(255,255,255,0.12)';
    }
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(node.x, node.y, nodeRadius, 0, 2 * Math.PI);
    ctx.stroke();

    // ====================================================================
    //  LAYER 4 — Labels (always visible at globalScale >= 0.6)
    // ====================================================================
    if (globalScale >= 0.6 && !isDimmed) {
        const label = node.id;
        const fontSize = Math.min(13, Math.max(8, 11 / globalScale));
        ctx.font = `500 ${fontSize}px Inter, system-ui, -apple-system, sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';

        const textWidth = ctx.measureText(label).width;
        const padX = 6;
        const padY = 4;
        const pillW = textWidth + padX * 2;
        const pillH = fontSize + padY * 2;
        const labelY = node.y - nodeRadius - pillH / 2 - 4;
        const pillR = pillH / 2;

        // Dark pill background
        ctx.fillStyle = 'rgba(0,0,0,0.55)';
        ctx.beginPath();
        ctx.roundRect(node.x - pillW / 2, labelY - pillH / 2, pillW, pillH, pillR);
        ctx.fill();

        // Text
        ctx.fillStyle = 'rgba(255,255,255,0.92)';
        ctx.fillText(label, node.x, labelY);
    }
}

// ---------- relation label painter ----------

/**
 * Paint relation labels on links when zoomed in.
 * Used as linkCanvasObject callback.
 */
export function paintLinkLabel(link, ctx, globalScale, tier) {
    if (globalScale < 1.2) return;

    const rawLabel = link.label;
    if (!rawLabel) return;
    const label = rawLabel.length > 20 ? rawLabel.slice(0, 20) + '\u2026' : rawLabel;

    const source = link.source;
    const target = link.target;
    if (!source || !target || typeof source.x !== 'number') return;
    if (!isFinite(source.x) || !isFinite(target.x)) return;

    const midX = (source.x + target.x) / 2;
    const midY = (source.y + target.y) / 2;

    const fontSize = 9;
    ctx.font = `400 ${fontSize}px Inter, system-ui, sans-serif`;

    const textWidth = ctx.measureText(label).width;
    const padX = 5;
    const padY = 3;
    const pillW = textWidth + padX * 2;
    const pillH = fontSize + padY * 2;
    const pillR = pillH / 2;

    // Background pill
    ctx.fillStyle = 'rgba(15, 23, 42, 0.85)';
    ctx.beginPath();
    ctx.roundRect(midX - pillW / 2, midY - pillH / 2, pillW, pillH, pillR);
    ctx.fill();

    // Subtle border
    ctx.strokeStyle = 'rgba(100, 116, 139, 0.2)';
    ctx.lineWidth = 0.5;
    ctx.stroke();

    // Text
    ctx.fillStyle = '#CBD5E1';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(label, midX, midY);
}

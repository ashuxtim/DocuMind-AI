import { useCallback, useRef } from 'react';

/**
 * Hook that manages graph hover/highlight state via refs to avoid React re-renders.
 * The canvas repaints every frame anyway, so React state is unnecessary for this data.
 *
 * @param {object} data - Graph data { nodes, links }
 * @returns {{ handleNodeHover, paintStateRef, hoveredNodeRef }}
 */
export function useGraphHighlight(data) {
    const hoveredNodeRef = useRef(null);
    const paintStateRef = useRef({
        hoveredId: null,
        neighborIds: new Set(),
        highlightLinks: new Set(),
        tier: null,
        viewport: null,
    });

    const handleNodeHover = useCallback(
        (node) => {
            hoveredNodeRef.current = node;

            if (node) {
                const neighbors = new Set();
                const links = new Set();

                data.links.forEach((link) => {
                    const sourceId = typeof link.source === 'object' ? link.source.id : link.source;
                    const targetId = typeof link.target === 'object' ? link.target.id : link.target;

                    if (sourceId === node.id) {
                        neighbors.add(targetId);
                        links.add(link);
                    }
                    if (targetId === node.id) {
                        neighbors.add(sourceId);
                        links.add(link);
                    }
                });

                neighbors.add(node.id);
                paintStateRef.current.hoveredId = node.id;
                paintStateRef.current.neighborIds = neighbors;
                paintStateRef.current.highlightLinks = links;
            } else {
                paintStateRef.current.hoveredId = null;
                paintStateRef.current.neighborIds = new Set();
                paintStateRef.current.highlightLinks = new Set();
            }
        },
        [data.links]
    );

    return { handleNodeHover, paintStateRef, hoveredNodeRef };
}

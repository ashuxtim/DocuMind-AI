import { useState, useCallback, useEffect, useRef } from 'react';
import { getGraph } from '@/lib/api';
import { getGraphTier } from '@/utils/graphConfig';

/**
 * Hook for fetching and processing graph data.
 * Computes node degrees, sizes, and determines the performance tier.
 *
 * @param {object} options
 * @param {number} [options.limit=2000] - Max edges to request from backend
 * @returns {{ data, loading, tier, totalCount, refetch }}
 */
export function useGraphData({ limit = 2000 } = {}) {
    const [data, setData] = useState({ nodes: [], links: [] });
    const [loading, setLoading] = useState(true);
    const [totalCount, setTotalCount] = useState(0);
    const [tier, setTier] = useState(null);
    const prevHashRef = useRef(null);

    const fetchGraph = useCallback(async () => {
        setLoading(true);

        try {
            const response = await getGraph(limit);
            const graphData = response.data;

            // Use server-side degree if available, otherwise compute client-side
            const hasServerDegree = graphData.nodes.length > 0 && graphData.nodes[0].degree !== undefined;

            if (!hasServerDegree) {
                const nodeDegrees = {};
                graphData.links.forEach((link) => {
                    nodeDegrees[link.source] = (nodeDegrees[link.source] || 0) + 1;
                    nodeDegrees[link.target] = (nodeDegrees[link.target] || 0) + 1;
                });
                graphData.nodes.forEach((node) => {
                    node.connections = nodeDegrees[node.id] || 1;
                    node.val = Math.max(2, Math.log2((nodeDegrees[node.id] || 1) + 1) * 4);
                });
            } else {
                graphData.nodes.forEach((node) => {
                    node.connections = node.degree || 1;
                    node.val = Math.max(2, Math.log2((node.degree || 1) + 1) * 4);
                });
            }

            // Determine performance tier
            const currentTier = getGraphTier(graphData.nodes.length);

            // Stable reference check — don't re-set if data hasn't changed
            const hash = graphData.nodes.length + ':' + graphData.links.length;
            if (hash !== prevHashRef.current) {
                prevHashRef.current = hash;
                setData(graphData);
                setTier(currentTier);
                setTotalCount(graphData.total || graphData.nodes.length);
            }
        } catch (error) {
            console.error('Failed to fetch graph', error);
        } finally {
            setLoading(false);
        }
    }, [limit]);

    useEffect(() => {
        fetchGraph();
    }, [fetchGraph]);

    return { data, loading, tier, totalCount, refetch: fetchGraph };
}

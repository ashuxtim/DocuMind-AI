import { useState, useEffect, useCallback } from 'react';
import { MultiGraph } from 'graphology';
import { assign as forceAtlas2Assign } from 'graphology-layout-forceatlas2';
import { getGraph } from '@/lib/api';

const COLOR_MAP = {
  Person: '#34D399',
  Organization: '#FBBF24',
  Statute: '#A78BFA',
  Date: '#22D3EE',
  Document: '#F472B6',
  Entity: '#94A3B8',
};

function nodeSize(degree) {
  return Math.max(5, Math.min(30, 5 + Math.log(degree + 1) * 6));
}

export function useGraphData() {
  const [graph, setGraph] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [nodeCount, setNodeCount] = useState(0);
  const [linkCount, setLinkCount] = useState(0);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getGraph(2000);
      const { nodes, links } = res.data;

      const g = new MultiGraph();

      nodes.forEach((node) => {
        g.addNode(node.id, {
          x: Math.random() * 1000 - 500,
          y: Math.random() * 1000 - 500,
          size: nodeSize(node.degree || 1),
          color: COLOR_MAP[node.group] ?? COLOR_MAP.Entity,
          label: node.id,
          group: node.group,
        });
      });

      links.forEach((link) => {
        if (g.hasNode(link.source) && g.hasNode(link.target)) {
          g.addEdge(link.source, link.target, {
            label: link.label ?? '',
            color: 'rgba(148, 163, 184, 0.4)',
            size: 1,
          });
        }
      });

      // Run ForceAtlas2 synchronously before sigma mounts so nodes have real positions
      if (g.order > 0) {
        forceAtlas2Assign(g, {
          iterations: 500,
          settings: {
            gravity: 0.05,
            scalingRatio: 10,
            strongGravityMode: false,
            barnesHutOptimize: true,
            barnesHutTheta: 0.5,
            adjustSizes: true,
            linLogMode: false,
            outboundAttractionDistribution: true,
          },
        });
      }

      setGraph(g);
      setNodeCount(g.order);
      setLinkCount(g.size);
    } catch (err) {
      setError(err?.message ?? 'Failed to load graph');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { graph, loading, error, refetch: fetchData, nodeCount, linkCount };
}

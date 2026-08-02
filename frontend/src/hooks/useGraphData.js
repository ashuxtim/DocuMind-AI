import { useState, useEffect, useCallback } from 'react';
import { MultiGraph } from 'graphology';
import { assign as forceAtlas2Assign } from 'graphology-layout-forceatlas2';
import noverlap from 'graphology-layout-noverlap';
import { getGraph } from '@/lib/api';

const COLOR_MAP = {
  Person: '#34D399',
  Organization: '#FBBF24',
  Statute: '#A78BFA',
  Date: '#22D3EE',
  Document: '#F472B6',
  Entity: '#94A3B8',
};

// Refined base node size formula matching GitNexus scale (4px to 16px)
function nodeSize(degree) {
  return Math.max(4, Math.min(16, 4 + Math.log(degree + 1) * 3));
}

const NOVERLAP_SETTINGS = {
  maxIterations: 25,
  ratio: 1.1,
  margin: 10,
  expansion: 1.05,
};

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
            color: '#2a2a3a',
            size: 1,
          });
        }
      });

      // Run ForceAtlas2 + Noverlap anti-collision matching GitNexus graph distribution
      if (g.order > 0) {
        forceAtlas2Assign(g, {
          iterations: 300,
          settings: {
            gravity: 0.3,
            scalingRatio: 30,
            slowDown: 2,
            strongGravityMode: false,
            barnesHutOptimize: true,
            barnesHutTheta: 0.6,
            adjustSizes: true,
            linLogMode: false,
            outboundAttractionDistribution: true,
          },
        });

        // Anti-collision pass to eliminate node overlap in dense entity clusters
        noverlap.assign(g, NOVERLAP_SETTINGS);
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


import { useEffect, useRef, useImperativeHandle, forwardRef } from 'react';
import { Sigma } from 'sigma';
import { EdgeArrowProgram } from 'sigma/rendering';

const SIGMA_SETTINGS = {
  renderEdgeLabels: true,
  defaultEdgeColor: 'rgba(148, 163, 184, 0.4)',
  defaultEdgeType: 'arrow',
  edgeProgramClasses: { arrow: EdgeArrowProgram },
  labelFont: 'Inter, system-ui, sans-serif',
  labelSize: 12,
  labelColor: { color: '#ffffff' },
  labelWeight: '500',
  edgeLabelSize: 9,
  edgeLabelColor: { color: '#94A3B8' },
  minCameraRatio: 0.05,
  maxCameraRatio: 5,
  edgeLabelThreshold: 8,
};

const GraphExplorer = forwardRef(function GraphExplorer({ graph, search }, ref) {
  const containerRef = useRef(null);
  const sigmaRef = useRef(null);
  const hoveredNodeRef = useRef(null);

  // Mount sigma after the container div is in the DOM
  useEffect(() => {
    if (!graph || !containerRef.current) return;

    const sigma = new Sigma(graph, containerRef.current, {
      ...SIGMA_SETTINGS,
      nodeReducer: (node, data) => {
        const hovered = hoveredNodeRef.current;
        if (!hovered) return data;
        if (node === hovered) return { ...data, highlighted: true, zIndex: 1 };
        const neighbors = graph.neighbors(hovered);
        if (neighbors.includes(node)) return { ...data, zIndex: 1 };
        // Dim non-neighbors: append 33 for ~20% opacity in 8-digit hex
        const dimColor =
          data.color.startsWith('#') && data.color.length === 7
            ? data.color + '33'
            : 'rgba(148,163,184,0.15)';
        return { ...data, color: dimColor, label: '', size: data.size * 0.6 };
      },
      edgeReducer: (edge, data) => {
        const hovered = hoveredNodeRef.current;
        if (!hovered) return data;
        const source = graph.source(edge);
        const target = graph.target(edge);
        if (source === hovered || target === hovered) return data;
        return { ...data, hidden: true };
      },
    });

    sigmaRef.current = sigma;

    // Store the original label once so it is never lost during LOD updates
    graph.forEachNode((nodeId, attrs) => {
      graph.setNodeAttribute(nodeId, '_label', attrs.label);
    });

    // Zoom-based label level-of-detail: higher ratio = more zoomed out
    const handleCameraUpdate = () => {
      const ratio = sigma.getCamera().ratio;
      graph.forEachNode((nodeId, attrs) => {
        if (ratio > 1.5) {
          // Very zoomed out — only hub nodes (size >= 18)
          graph.setNodeAttribute(nodeId, 'label', attrs.size >= 18 ? attrs._label : '');
        } else if (ratio > 0.6) {
          // Mid zoom — medium and large nodes (size >= 10)
          graph.setNodeAttribute(nodeId, 'label', attrs.size >= 10 ? attrs._label : '');
        } else {
          // Zoomed in — show all labels
          graph.setNodeAttribute(nodeId, 'label', attrs._label);
        }
      });
      sigma.refresh();
    };

    sigma.getCamera().on('updated', handleCameraUpdate);
    // Apply correct labels for the initial zoom level immediately
    sigma.getCamera().emit('updated');

    // Hover: highlight neighborhood, dim the rest
    sigma.on('enterNode', ({ node }) => {
      hoveredNodeRef.current = node;
      sigma.refresh();
    });
    sigma.on('leaveNode', () => {
      hoveredNodeRef.current = null;
      sigma.refresh();
    });

    // Click: animate camera to the clicked node
    sigma.on('clickNode', ({ node }) => {
      const pos = sigma.getNodeDisplayData(node);
      if (pos) {
        sigma.getCamera().animate(
          { x: pos.x, y: pos.y, ratio: 0.3 },
          { duration: 600 },
        );
      }
    });

    return () => {
      sigma.kill();
      sigmaRef.current = null;
      hoveredNodeRef.current = null;
    };
  }, [graph]);

  // Fly camera to searched node
  useEffect(() => {
    if (!search || !sigmaRef.current || !graph) return;
    const term = search.toLowerCase();
    let found = null;
    graph.forEachNode((node) => {
      if (!found && node.toLowerCase().includes(term)) {
        found = node;
      }
    });
    if (found) {
      const pos = sigmaRef.current.getNodeDisplayData(found);
      if (pos) {
        sigmaRef.current.getCamera().animate(
          { x: pos.x, y: pos.y, ratio: 0.3 },
          { duration: 600 },
        );
      }
    }
  }, [search, graph]);

  // Expose camera controls to parent via ref
  useImperativeHandle(ref, () => ({
    zoomIn() {
      if (!sigmaRef.current) return;
      const cam = sigmaRef.current.getCamera();
      cam.animate({ ratio: cam.ratio * 0.7 }, { duration: 300 });
    },
    zoomOut() {
      if (!sigmaRef.current) return;
      const cam = sigmaRef.current.getCamera();
      cam.animate({ ratio: cam.ratio * 1.4 }, { duration: 300 });
    },
    fitView() {
      if (!sigmaRef.current) return;
      sigmaRef.current.getCamera().animatedReset();
    },
  }));

  return (
    <div
      ref={containerRef}
      style={{ width: '100%', height: '100%' }}
    />
  );
});

export default GraphExplorer;

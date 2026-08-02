import { useEffect, useRef, useImperativeHandle, forwardRef } from 'react';
import { Sigma } from 'sigma';
import { EdgeArrowProgram } from 'sigma/rendering';

// Color manipulation helpers matching GitNexus
const hexToRgb = (hex) => {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return result
    ? {
        r: parseInt(result[1], 16),
        g: parseInt(result[2], 16),
        b: parseInt(result[3], 16),
      }
    : { r: 148, g: 163, b: 184 };
};

const rgbToHex = (r, g, b) => {
  return (
    '#' +
    [r, g, b]
      .map((x) => {
        const hex = Math.max(0, Math.min(255, Math.round(x))).toString(16);
        return hex.length === 1 ? '0' + hex : hex;
      })
      .join('')
  );
};

// Dim a color by mixing with dark background #12121c (GitNexus dimming)
const dimColor = (hex, amount) => {
  const rgb = hexToRgb(hex);
  const darkBg = { r: 18, g: 18, b: 28 }; // #12121c dark background
  return rgbToHex(
    darkBg.r + (rgb.r - darkBg.r) * amount,
    darkBg.g + (rgb.g - darkBg.g) * amount,
    darkBg.b + (rgb.b - darkBg.b) * amount,
  );
};

// Brighten a color for active highlights
const brightenColor = (hex, factor) => {
  const rgb = hexToRgb(hex);
  return rgbToHex(
    rgb.r + ((255 - rgb.r) * (factor - 1)) / factor,
    rgb.g + ((255 - rgb.g) * (factor - 1)) / factor,
    rgb.b + ((255 - rgb.b) * (factor - 1)) / factor,
  );
};

const SIGMA_SETTINGS = {
  renderLabels: true,
  labelFont: 'JetBrains Mono, monospace',
  labelSize: 11,
  labelWeight: '500',
  labelColor: { color: '#e4e4ed' },
  labelRenderedSizeThreshold: 8,
  labelDensity: 0.1,
  labelGridCellSize: 70,

  defaultNodeColor: '#94A3B8',
  defaultEdgeColor: '#2a2a3a',

  defaultEdgeType: 'arrow',
  edgeProgramClasses: { arrow: EdgeArrowProgram },

  // Custom GitNexus hover card renderer - dark pill with colored border & glow ring
  defaultDrawNodeHover: (context, data, settings) => {
    const label = data.label;
    if (!label) return;

    const size = settings.labelSize || 11;
    const font = settings.labelFont || 'JetBrains Mono, monospace';
    const weight = settings.labelWeight || '500';

    context.font = `${weight} ${size}px ${font}`;
    const textWidth = context.measureText(label).width;

    const nodeSize = data.size || 8;
    const x = data.x;
    const y = data.y - nodeSize - 10;
    const paddingX = 8;
    const paddingY = 5;
    const height = size + paddingY * 2;
    const width = textWidth + paddingX * 2;
    const radius = 4;

    // Dark background pill
    context.fillStyle = '#12121c';
    context.beginPath();
    if (context.roundRect) {
      context.roundRect(x - width / 2, y - height / 2, width, height, radius);
    } else {
      context.rect(x - width / 2, y - height / 2, width, height);
    }
    context.fill();

    // Border matching node color
    context.strokeStyle = data.color || '#7c3aed';
    context.lineWidth = 2;
    context.stroke();

    // Label text - light color
    context.fillStyle = '#f5f5f7';
    context.textAlign = 'center';
    context.textBaseline = 'middle';
    context.fillText(label, x, y);

    // Subtle glow ring around node
    context.beginPath();
    context.arc(data.x, data.y, nodeSize + 4, 0, Math.PI * 2);
    context.strokeStyle = data.color || '#7c3aed';
    context.lineWidth = 2;
    context.globalAlpha = 0.5;
    context.stroke();
    context.globalAlpha = 1;
  },

  minCameraRatio: 0.002,
  maxCameraRatio: 50,
  hideEdgesOnMove: true,
  zIndex: true,
};

const GraphExplorer = forwardRef(function GraphExplorer(
  { graph, search, activeTypes, onTypeCounts, onGraphReady },
  ref,
) {
  const containerRef = useRef(null);
  const sigmaRef = useRef(null);
  const hoveredNodeRef = useRef(null);
  const selectedNodeRef = useRef(null);
  const activeTypesRef = useRef(activeTypes);

  // Mount sigma after container div is available
  useEffect(() => {
    if (!graph || !containerRef.current) return;

    const sigma = new Sigma(graph, containerRef.current, {
      ...SIGMA_SETTINGS,
      nodeReducer: (node, data) => {
        const res = { ...data };

        // Hide node if type is toggled off
        if (activeTypesRef.current && !activeTypesRef.current.has(data.group)) {
          res.hidden = true;
          return res;
        }

        const activeNode = hoveredNodeRef.current || selectedNodeRef.current;

        if (activeNode) {
          const isTargetNode = node === activeNode;
          const isNeighbor = graph.hasEdge(node, activeNode) || graph.hasEdge(activeNode, node);

          if (isTargetNode) {
            res.color = data.color;
            res.size = (data.size || 8) * 1.8;
            res.zIndex = 2;
            res.highlighted = true;
          } else if (isNeighbor) {
            res.color = data.color;
            res.size = (data.size || 8) * 1.3;
            res.zIndex = 1;
          } else {
            res.color = dimColor(data.color, 0.25);
            res.size = (data.size || 8) * 0.6;
            res.zIndex = 0;
          }
        }

        return res;
      },
      edgeReducer: (edge, data) => {
        const res = { ...data };

        // Hide edge if endpoint types are toggled off
        if (activeTypesRef.current) {
          const srcGroup = graph.getNodeAttribute(graph.source(edge), 'group');
          const tgtGroup = graph.getNodeAttribute(graph.target(edge), 'group');
          if (!activeTypesRef.current.has(srcGroup) || !activeTypesRef.current.has(tgtGroup)) {
            res.hidden = true;
            return res;
          }
        }

        const activeNode = hoveredNodeRef.current || selectedNodeRef.current;

        if (activeNode) {
          const source = graph.source(edge);
          const target = graph.target(edge);
          const isConnected = source === activeNode || target === activeNode;

          if (isConnected) {
            res.color = brightenColor(data.color || '#94A3B8', 1.5);
            res.size = Math.max(3, (data.size || 1) * 3.5);
            res.zIndex = 2;
          } else {
            res.color = dimColor(data.color || '#94A3B8', 0.1);
            res.size = 0.3;
            res.zIndex = 0;
          }
        }

        return res;
      },
    });

    sigmaRef.current = sigma;

    // Store original labels for level-of-detail management
    graph.forEachNode((nodeId, attrs) => {
      graph.setNodeAttribute(nodeId, '_label', attrs.label);
    });

    // Report type counts
    const counts = {};
    graph.forEachNode((id, attrs) => {
      counts[attrs.group] = (counts[attrs.group] || 0) + 1;
    });
    onTypeCounts?.(counts);
    onGraphReady?.(graph);

    // Zoom-based level-of-detail: adjust labels dynamically
    const handleCameraUpdate = () => {
      const ratio = sigma.getCamera().ratio;
      graph.forEachNode((nodeId, attrs) => {
        if (ratio > 2.5) {
          graph.setNodeAttribute(nodeId, 'label', attrs.size >= 18 ? attrs._label : '');
        } else if (ratio > 0.8) {
          graph.setNodeAttribute(nodeId, 'label', attrs.size >= 10 ? attrs._label : '');
        } else {
          graph.setNodeAttribute(nodeId, 'label', attrs._label);
        }
      });
      sigma.refresh();
    };

    sigma.getCamera().on('updated', handleCameraUpdate);
    sigma.getCamera().emit('updated');

    // Event handlers with pointer cursor feedback
    sigma.on('enterNode', ({ node }) => {
      hoveredNodeRef.current = node;
      if (containerRef.current) containerRef.current.style.cursor = 'pointer';
      sigma.refresh();
    });

    sigma.on('leaveNode', () => {
      hoveredNodeRef.current = null;
      if (containerRef.current) containerRef.current.style.cursor = 'default';
      sigma.refresh();
    });

    sigma.on('clickNode', ({ node }) => {
      selectedNodeRef.current = node;
      const pos = sigma.getNodeDisplayData(node);
      if (pos) {
        sigma.getCamera().animate(
          { x: pos.x, y: pos.y, ratio: 0.25 },
          { duration: 500 },
        );
      }
      // Nudge ratio slightly to force edge re-rendering cache flush (GitNexus trick)
      const camera = sigma.getCamera();
      camera.animate({ ratio: camera.ratio * 1.0001 }, { duration: 50 });
      sigma.refresh();
    });

    sigma.on('clickStage', () => {
      selectedNodeRef.current = null;
      sigma.refresh();
    });

    return () => {
      sigma.kill();
      sigmaRef.current = null;
      hoveredNodeRef.current = null;
      selectedNodeRef.current = null;
    };
  }, [graph]);

  // Camera fly animation when search is triggered
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
      selectedNodeRef.current = found;
      const pos = sigmaRef.current.getNodeDisplayData(found);
      if (pos) {
        sigmaRef.current.getCamera().animate(
          { x: pos.x, y: pos.y, ratio: 0.25 },
          { duration: 600 },
        );
      }
      sigmaRef.current.refresh();
    }
  }, [search, graph]);

  // Sync activeTypes filter changes
  useEffect(() => {
    activeTypesRef.current = activeTypes;
    if (sigmaRef.current) sigmaRef.current.refresh();
  }, [activeTypes]);

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
      sigmaRef.current.getCamera().animatedReset({ duration: 600 });
    },
  }));

  return <div ref={containerRef} className="w-full h-full" />;
});

export default GraphExplorer;


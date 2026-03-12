// --- Graph Performance Tier Configuration ---
// Auto-selects rendering features based on node count.

const TIERS = {
    small: {
        maxNodes: 500,
        showGlow: true,
        showLabelsAtScale: 1.5,
        showEdgesAtScale: 0,        // always show
        showRelationLabelsAtScale: 2.0,
        showParticlesOnHover: true,
        particleCount: 2,
        explosionEnabled: true,
        ambientGlow: true,
        labelDegreeThreshold: 0,    // show all labels when zoomed
        d3VelocityDecay: 0.25,
        warmupTicks: 50,
        cooldownTicks: 200,
    },
    medium: {
        maxNodes: 2000,
        showGlow: true,
        showLabelsAtScale: 2.0,
        showEdgesAtScale: 0,
        showRelationLabelsAtScale: 2.5,
        showParticlesOnHover: true,
        particleCount: 1,
        explosionEnabled: false,
        ambientGlow: true,
        labelDegreeThreshold: 2,    // only show labels for degree > 2
        d3VelocityDecay: 0.35,
        warmupTicks: 80,
        cooldownTicks: 300,
    },
    large: {
        maxNodes: Infinity,
        showGlow: false,
        showLabelsAtScale: 2.5,
        showEdgesAtScale: 0.2,
        showRelationLabelsAtScale: 3.0,
        showParticlesOnHover: false,
        particleCount: 0,
        explosionEnabled: false,
        ambientGlow: false,
        labelDegreeThreshold: 5,
        d3VelocityDecay: 0.4,
        warmupTicks: 100,
        cooldownTicks: 400,
    },
};

/**
 * Returns the appropriate config tier based on the number of nodes.
 * @param {number} nodeCount
 * @returns {object} tier config
 */
export function getGraphTier(nodeCount) {
    if (nodeCount <= TIERS.small.maxNodes) return TIERS.small;
    if (nodeCount <= TIERS.medium.maxNodes) return TIERS.medium;
    return TIERS.large;
}

export default TIERS;

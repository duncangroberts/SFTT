
const COLORS = [
  '#4E79A7', '#F28E2B', '#E15759', '#76B7B2', '#59A14F',
  '#EDC948', '#B07AA1', '#FF9DA7', '#9C755F', '#BAB0AC',
  '#ff6b35', '#3ab4f2', '#5ad1a4', '#b353ff', '#ff8c00',
  '#00ced1', '#ff1493', '#32cd32',
];

const FIXED_COLORS = {
  'generative ai': '#f7c843', // Yellow
  'blockchain': '#f2545b',    // Red
};

// Simple hash function to get a deterministic index for a string
const getHash = (str) => {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = (hash << 5) - hash + char;
    hash |= 0; // Convert to 32bit integer
  }
  return Math.abs(hash);
};

const assignedColors = new Set(Object.values(FIXED_COLORS));

export const getColor = (techName) => {
  const lowerTechName = techName.toLowerCase();

  if (FIXED_COLORS[lowerTechName]) {
    return FIXED_COLORS[lowerTechName];
  }

  const availableColors = COLORS.filter(c => !assignedColors.has(c));
  if (availableColors.length === 0) {
    // Fallback if all main colors are used
    return COLORS[getHash(lowerTechName) % COLORS.length];
  }

  const index = getHash(lowerTechName) % availableColors.length;
  const color = availableColors[index];
  
  // This part is tricky in a stateless way without a global registry.
  // For now, we accept potential collisions if available colors run out.
  // A better approach for more items would be a global state management.

  return color;
};

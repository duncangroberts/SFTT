import domainConfig from './trajectoryDomainConfig.json';

const DEFAULT_PADDING = 0.05;

const toFiniteNumbers = (values = []) =>
  values
    .map((value) => Number(value))
    .filter((value) => Number.isFinite(value));

const normalizeAxisConfig = (axisConfig) => {
  if (!axisConfig) {
    return {
      center: 0,
      halfRange: 1,
      padding: DEFAULT_PADDING,
    };
  }

  const min = Number(axisConfig.min);
  const max = Number(axisConfig.max);
  const padding =
    typeof axisConfig.padding === 'number' ? Math.max(axisConfig.padding, 0) : DEFAULT_PADDING;

  if (Number.isFinite(min) && Number.isFinite(max) && max > min) {
    const center = (min + max) / 2;
    const halfRange = (max - min) / 2;
    return { center, halfRange, padding };
  }

  const center = Number(axisConfig.center) || 0;
  const halfRange = Math.max(Number(axisConfig.halfRange) || 1, 0.5);

  return {
    center,
    halfRange,
    padding,
  };
};

const buildDomain = (values, baseAxisConfig) => {
  const axisConfig = normalizeAxisConfig(baseAxisConfig);
  const numericValues = toFiniteNumbers(values);

  if (!numericValues.length) {
    const min = axisConfig.center - axisConfig.halfRange;
    const max = axisConfig.center + axisConfig.halfRange;
    return { min, max, center: axisConfig.center };
  }

  const { center, padding } = axisConfig;
  let requiredHalfRange = axisConfig.halfRange;

  numericValues.forEach((value) => {
    const distance = Math.abs(value - center);
    if (distance + padding > requiredHalfRange) {
      requiredHalfRange = distance + padding;
    }
  });

  return {
    min: center - requiredHalfRange,
    max: center + requiredHalfRange,
    center,
  };
};

export const computeTrajectoryDomains = (records = []) => {
  const momentumValues = [];
  const convictionValues = [];

  if (Array.isArray(records)) {
    records.forEach((record) => {
      if (!record) {
        return;
      }
      const momentum = Number(record.momentum);
      const conviction = Number(record.conviction);
      if (Number.isFinite(momentum)) {
        momentumValues.push(momentum);
      }
      if (Number.isFinite(conviction)) {
        convictionValues.push(conviction);
      }
    });
  }

  const momentumDomain = buildDomain(momentumValues, domainConfig.momentum);
  const convictionDomain = buildDomain(convictionValues, domainConfig.conviction);

  return {
    momentum: [momentumDomain.min, momentumDomain.max],
    conviction: [convictionDomain.min, convictionDomain.max],
    midMomentum: momentumDomain.center,
    midConviction: convictionDomain.center,
  };
};

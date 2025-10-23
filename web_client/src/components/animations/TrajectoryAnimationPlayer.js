import React, { useEffect, useState } from 'react';

const BASE_SEGMENT_DURATION = 3000; // ms per segment at 1x speed
const CANVAS_WIDTH = 640;
const CANVAS_HEIGHT = 420;
const CANVAS_PADDING = 60;

const formatMonthLabel = (value) => {
  if (!value) {
    return 'Unknown';
  }

  const timeFromHyphen = () => {
    const [year, month] = value.split('-').map((part) => parseInt(part, 10));
    if (!Number.isFinite(year) || !Number.isFinite(month)) {
      return null;
    }
    return new Date(year, month - 1, 1);
  };

  const parsed = timeFromHyphen() || new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return String(value);
  }

  return parsed.toLocaleDateString(undefined, {
    month: 'short',
    year: 'numeric',
  });
};

const clamp = (value, min, max) => Math.min(Math.max(value, min), max);

function TrajectoryAnimationPlayer({ techName, points, momentumDomain, convictionDomain }) {
  const [isPlaying, setIsPlaying] = useState(true);
  const [animationState, setAnimationState] = useState({ segmentIndex: 0, segmentProgress: 0 });
  const [speed, setSpeed] = useState(1);
  const totalMonths = points.length;
  const speedDisplay = Number(speed)
    .toFixed(2)
    .replace(/\.00$/, '')
    .replace(/(\.\d)0$/, '$1');

  // Reset animation when the data set changes
  useEffect(() => {
    setAnimationState({ segmentIndex: 0, segmentProgress: 0 });
    setIsPlaying(true);
  }, [points]);

  useEffect(() => {
    if (!isPlaying || points.length < 2) {
      return undefined;
    }

    let rafId = null;
    let lastTimestamp = null;

    const step = (timestamp) => {
      if (lastTimestamp === null) {
        lastTimestamp = timestamp;
        rafId = requestAnimationFrame(step);
        return;
      }

      const delta = timestamp - lastTimestamp;
      lastTimestamp = timestamp;

      let shouldStop = false;

      setAnimationState((prev) => {
        let segmentIndex = clamp(prev.segmentIndex, 0, points.length - 2);
        let segmentProgress = clamp(prev.segmentProgress, 0, 1);

        const progressIncrement = (delta * speed) / BASE_SEGMENT_DURATION;
        segmentProgress += progressIncrement;

        while (segmentProgress >= 1 && segmentIndex < points.length - 2) {
          segmentProgress -= 1;
          segmentIndex += 1;
        }

        if (segmentProgress >= 1 && segmentIndex >= points.length - 2) {
          segmentProgress = 1;
          segmentIndex = Math.min(segmentIndex, points.length - 2);
          shouldStop = true;
        }

        return { segmentIndex, segmentProgress };
      });

      if (shouldStop) {
        setIsPlaying(false);
        return;
      }

      rafId = requestAnimationFrame(step);
    };

    rafId = requestAnimationFrame(step);

    return () => {
      if (rafId) {
        cancelAnimationFrame(rafId);
      }
    };
  }, [isPlaying, points, speed]);

  if (points.length < 2) {
    return (
      <div className="trajectory-animation-empty">
        <p>Not enough monthly data to animate this trajectory yet.</p>
      </div>
    );
  }

  const { segmentIndex, segmentProgress } = animationState;

  const momentumMin = Number.isFinite(momentumDomain?.[0]) ? momentumDomain[0] : -5;
  const momentumMax = Number.isFinite(momentumDomain?.[1]) ? momentumDomain[1] : 5;
  const convictionMin = Number.isFinite(convictionDomain?.[0]) ? convictionDomain[0] : -5;
  const convictionMax = Number.isFinite(convictionDomain?.[1]) ? convictionDomain[1] : 5;

  const momentumRange = momentumMax - momentumMin || 1;
  const convictionRange = convictionMax - convictionMin || 1;

  const projectX = (value) => {
    const ratio = (value - momentumMin) / momentumRange;
    return CANVAS_PADDING + clamp(ratio, 0, 1) * (CANVAS_WIDTH - CANVAS_PADDING * 2);
  };

  const projectY = (value) => {
    const ratio = (value - convictionMin) / convictionRange;
    const inverted = 1 - clamp(ratio, 0, 1);
    return CANVAS_PADDING + inverted * (CANVAS_HEIGHT - CANVAS_PADDING * 2);
  };

  const safeSegmentIndex = clamp(segmentIndex, 0, points.length - 2);
  const startPoint = points[safeSegmentIndex];
  const endPoint = points[safeSegmentIndex + 1] || startPoint;
  const easedProgress = clamp(segmentProgress, 0, 1);

  const currentMomentum = startPoint.momentum + (endPoint.momentum - startPoint.momentum) * easedProgress;
  const currentConviction = startPoint.conviction + (endPoint.conviction - startPoint.conviction) * easedProgress;

  const totalSegments = Math.max(points.length - 1, 1);

  const currentLabel = `${formatMonthLabel(startPoint.month)} → ${formatMonthLabel(endPoint.month)}`;
  const currentMonthLabel = easedProgress < 0.5 ? formatMonthLabel(startPoint.month) : formatMonthLabel(endPoint.month);

  const deltaMomentum = points[points.length - 1].momentum - points[0].momentum;
  const deltaConviction = points[points.length - 1].conviction - points[0].conviction;

  const handleTogglePlay = () => setIsPlaying((prev) => !prev);

  const handleReset = () => {
    setAnimationState({ segmentIndex: 0, segmentProgress: 0 });
    setIsPlaying(false);
  };

  const handleRestart = () => {
    setAnimationState({ segmentIndex: 0, segmentProgress: 0 });
    setIsPlaying(true);
  };

  const handleSpeedChange = (event) => {
    const next = Number(event.target.value);
    if (Number.isFinite(next) && next > 0) {
      setSpeed(next);
    }
  };

  const midMomentum = momentumMin + (momentumMax - momentumMin) / 2;
  const midConviction = convictionMin + (convictionMax - convictionMin) / 2;
  const quadrantOffset = 120;
  const labelBounds = {
    xMin: CANVAS_PADDING + 40,
    xMax: CANVAS_WIDTH - CANVAS_PADDING - 40,
    yMin: CANVAS_PADDING + 30,
    yMax: CANVAS_HEIGHT - CANVAS_PADDING - 30,
  };
  const labelXRight = clamp(projectX(midMomentum) + quadrantOffset, labelBounds.xMin, labelBounds.xMax);
  const labelXLeft = clamp(projectX(midMomentum) - quadrantOffset, labelBounds.xMin, labelBounds.xMax);
  const labelYTop = clamp(projectY(midConviction) - quadrantOffset, labelBounds.yMin, labelBounds.yMax);
  const labelYBottom = clamp(projectY(midConviction) + quadrantOffset, labelBounds.yMin, labelBounds.yMax);

  const completedPoints = points.slice(0, safeSegmentIndex + 1);
  const trailPoints =
    easedProgress === 0
      ? completedPoints
      : [...completedPoints, { momentum: currentMomentum, conviction: currentConviction }];

  const trailPath = trailPoints
    .map((point, index) => {
      const prefix = index === 0 ? 'M' : 'L';
      return `${prefix}${projectX(point.momentum)} ${projectY(point.conviction)}`;
    })
    .join(' ');

  return (
    <div className="trajectory-animation-wrapper">
      <header className="trajectory-animation-header">
        <div>
          <h3>{techName}</h3>
          <p className="trajectory-animation-subtitle">
            Animating momentum vs. conviction over the latest {totalMonths} {totalMonths === 1 ? 'month' : 'months'}.
          </p>
        </div>
        <div className="trajectory-animation-summary">
          <div>
            <span className="label">Δ Momentum</span>
            <span className={`value ${deltaMomentum >= 0 ? 'positive' : 'negative'}`}>{deltaMomentum.toFixed(2)}</span>
          </div>
          <div>
            <span className="label">Δ Conviction</span>
            <span className={`value ${deltaConviction >= 0 ? 'positive' : 'negative'}`}>{deltaConviction.toFixed(2)}</span>
          </div>
        </div>
      </header>

      <div className="trajectory-animation-canvas">
        <svg width={CANVAS_WIDTH} height={CANVAS_HEIGHT} role="img" aria-label={`Trajectory animation for ${techName}`}>
          {/* Background */}
          <rect x="0" y="0" width={CANVAS_WIDTH} height={CANVAS_HEIGHT} fill="#0d0d0d" rx="12" />

          {/* Axes */}
          <line
            x1={CANVAS_PADDING}
            y1={CANVAS_HEIGHT - CANVAS_PADDING}
            x2={CANVAS_WIDTH - CANVAS_PADDING}
            y2={CANVAS_HEIGHT - CANVAS_PADDING}
            stroke="#333"
            strokeWidth="2"
          />
          <line
            x1={CANVAS_PADDING}
            y1={CANVAS_PADDING}
            x2={CANVAS_PADDING}
            y2={CANVAS_HEIGHT - CANVAS_PADDING}
            stroke="#333"
            strokeWidth="2"
          />

          {/* Quadrant dividers */}
          <line
            x1={projectX(midMomentum)}
            y1={CANVAS_PADDING}
            x2={projectX(midMomentum)}
            y2={CANVAS_HEIGHT - CANVAS_PADDING}
            stroke="rgba(255,255,255,0.12)"
            strokeDasharray="6 6"
          />
          <line
            x1={CANVAS_PADDING}
            y1={projectY(midConviction)}
            x2={CANVAS_WIDTH - CANVAS_PADDING}
            y2={projectY(midConviction)}
            stroke="rgba(255,255,255,0.12)"
            strokeDasharray="6 6"
          />

          <text x={CANVAS_WIDTH / 2} y={CANVAS_HEIGHT - CANVAS_PADDING + 40} fill="#aaa" textAnchor="middle">
            Momentum
          </text>
          <text
            x={CANVAS_PADDING - 45}
            y={CANVAS_HEIGHT / 2}
            fill="#aaa"
            textAnchor="middle"
            transform={`rotate(-90 ${CANVAS_PADDING - 45} ${CANVAS_HEIGHT / 2})`}
          >
            Conviction
          </text>

          {/* Quadrant labels */}
          <text
            x={labelXRight}
            y={labelYTop}
            fill="#888"
            fontSize="14"
            textAnchor="middle"
          >
            Momentum Zone
          </text>
          <text
            x={labelXRight}
            y={labelYBottom}
            fill="#888"
            fontSize="14"
            textAnchor="middle"
          >
            Hype Trap
          </text>
          <text
            x={labelXLeft}
            y={labelYTop}
            fill="#888"
            fontSize="14"
            textAnchor="middle"
          >
            Hidden Gems
          </text>
          <text
            x={labelXLeft}
            y={labelYBottom}
            fill="#888"
            fontSize="14"
            textAnchor="middle"
          >
            Sceptics' Corner
          </text>

          {/* Path */}
          <path d={trailPath} fill="none" stroke="#ff6b35" strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" />

          {/* Keyframes */}
          {completedPoints.map((point, index) => (
            <g key={`${point.month}-${index}`}>
              <circle
                cx={projectX(point.momentum)}
                cy={projectY(point.conviction)}
                r={5}
                fill="rgba(255,255,255,0.18)"
                stroke="rgba(255,255,255,0.55)"
                strokeWidth="2"
              />
              <text
                x={projectX(point.momentum)}
                y={projectY(point.conviction) - 14}
                fill="#888"
                fontSize="13"
                textAnchor="middle"
              >
                {formatMonthLabel(point.month)}
              </text>
            </g>
          ))}

          {/* Animated marker */}
          <g>
            <circle
              cx={projectX(currentMomentum)}
              cy={projectY(currentConviction)}
              r="5"
              fill="#ff6b35"
              stroke="#ffffff"
              strokeWidth="2"
            />
            <text
              x={projectX(currentMomentum)}
              y={projectY(currentConviction) + 28}
              fill="#fff"
              fontSize="14"
              textAnchor="middle"
            >
              {currentMonthLabel}
            </text>
          </g>
        </svg>
      </div>

      <div className="trajectory-animation-panel">
        <div className="trajectory-animation-controls">
          <button type="button" onClick={handleTogglePlay} className="primary">
            {isPlaying ? 'Pause' : 'Play'}
          </button>
          <button type="button" onClick={handleReset}>
            Reset
          </button>
          <button type="button" onClick={handleRestart}>
            Restart &amp; Play
          </button>
          <div className="speed-selector">
            <span>Speed {speedDisplay}x</span>
            <input
              type="range"
              min="0.5"
              max="3"
              step="0.25"
              value={speed}
              onChange={handleSpeedChange}
            />
          </div>
        </div>

        <div className="trajectory-animation-stats">
          <div>
            <span className="label">Current Momentum</span>
            <span className="value">{currentMomentum.toFixed(2)}</span>
          </div>
          <div>
            <span className="label">Current Conviction</span>
            <span className="value">{currentConviction.toFixed(2)}</span>
          </div>
          <div className="current-window">
            <span className="label">Segment</span>
            <span className="value">{currentLabel}</span>
          </div>
        </div>

      </div>
    </div>
  );
}

export default TrajectoryAnimationPlayer;

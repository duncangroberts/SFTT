import React, { useEffect, useMemo, useRef, useState } from 'react';
import { collection, onSnapshot } from 'firebase/firestore';
import { db } from '../firebase';

const parseMonthToTimestamp = (value) => {
  if (!value && value !== 0) {
    return Number.NaN;
  }

  if (typeof value === 'number') {
    return value;
  }

  if (typeof value === 'string') {
    const parts = value.split('-');
    if (parts.length >= 2) {
      const year = parseInt(parts[0], 10);
      const month = parseInt(parts[1], 10);
      if (Number.isFinite(year) && Number.isFinite(month)) {
        return new Date(year, month - 1, 1).getTime();
      }
    }
    const parsed = new Date(value);
    if (!Number.isNaN(parsed.getTime())) {
      return parsed.getTime();
    }
  }

  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    return value.getTime();
  }

  return Number.NaN;
};

const formatMonth = (value) => {
  if (value === undefined || value === null) {
    return 'Unknown';
  }

  const timestamp = parseMonthToTimestamp(value);
  if (!Number.isFinite(timestamp)) {
    return String(value);
  }

  return new Date(timestamp).toLocaleDateString(undefined, {
    month: 'short',
    year: 'numeric',
  });
};

const buildTrajectorySummary = (entries) => {
  const techMap = new Map();

  entries.forEach((entry) => {
    if (!entry.tech_id) {
      return;
    }

    const techId = String(entry.tech_id);
    const techName = entry.tech_name || 'Unnamed Technology';
    const momentum = Number(entry.momentum) || 0;
    const conviction = Number(entry.conviction) || 0;
    const month = entry.month;
    const timestamp = parseMonthToTimestamp(month);

    if (!Number.isFinite(timestamp)) {
      return;
    }

    if (!techMap.has(techId)) {
      techMap.set(techId, {
        techId,
        techName,
        points: [],
      });
    }

    const record = techMap.get(techId);
    record.techName = techName;
    record.points.push({
      month,
      momentum,
      conviction,
      timestamp,
    });
  });

  return Array.from(techMap.values())
    .map((record) => {
      const sorted = record.points.sort((a, b) => a.timestamp - b.timestamp);
      const trimmed = sorted.slice(-3).map(({ timestamp, ...point }) => point);
      return {
        ...record,
        points: trimmed,
        hasFullHistory: trimmed.length === 3,
      };
    })
    .filter((record) => record.points.length >= 2)
    .sort((a, b) => a.techName.localeCompare(b.techName));
};

function TrajectoryTickerTab() {
  const BASE_SCROLL_SPEED_PX = 90; // pixels per second baseline

  const [rawData, setRawData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [speedMultiplier, setSpeedMultiplier] = useState(1);
  const [isPaused, setIsPaused] = useState(false);

  const tickerTrackRef = useRef(null);
  const tickerViewportRef = useRef(null);
  const animationFrameRef = useRef(null);
  const lastTimestampRef = useRef(null);
  const offsetRef = useRef(0);
  const baseWidthRef = useRef(0);
  const speedRef = useRef(speedMultiplier);
  const pausedRef = useRef(false);

  useEffect(() => {
    const sentimentCollection = collection(db, 'monthly_sentiment');
    const unsubscribe = onSnapshot(
      sentimentCollection,
      (snapshot) => {
        const nextData = [];
        snapshot.forEach((docSnapshot) => {
          const docData = docSnapshot.data();
          const momentum =
            (Number(docData.average_tone) || 0) +
            (Number(docData.analyst_lit_score) || 0) +
            (Number(docData.analyst_whimsy_score) || 0);
          const conviction =
            (Number(docData.hn_avg_compound) || 0) +
            (Number(docData.analyst_lit_score) || 0) +
            (Number(docData.analyst_whimsy_score) || 0);
          nextData.push({ ...docData, momentum, conviction });
        });
        setRawData(nextData);
        setLoading(false);
        setError(null);
      },
      (err) => {
        console.error('Error loading trajectory ticker data:', err);
        setError('Unable to load ticker data right now.');
        setLoading(false);
      }
    );

    return () => unsubscribe();
  }, []);

  const summaries = useMemo(() => buildTrajectorySummary(rawData), [rawData]);

  const tickerEntries = useMemo(() => {
    return summaries.map((summary) => {
      const latestPoint = summary.points[summary.points.length - 1];
      const earliestPoint = summary.points[0];
      const deltaMomentum = latestPoint.momentum - earliestPoint.momentum;
      const deltaConviction = latestPoint.conviction - earliestPoint.conviction;

      const rangeLabel = `${formatMonth(earliestPoint.month)} -> ${formatMonth(latestPoint.month)}`;

      return {
        techId: summary.techId,
        techName: summary.techName,
        hasFullHistory: summary.hasFullHistory,
        latestMonth: latestPoint.month,
        earliestMonth: earliestPoint.month,
        deltaMomentum,
        deltaConviction,
        rangeLabel,
      };
    });
  }, [summaries]);

  const handleSpeedChange = (event) => {
    const nextValue = Number(event.target.value);
    if (!Number.isFinite(nextValue) || nextValue <= 0) {
      return;
    }
    setSpeedMultiplier(nextValue);
  };

  useEffect(() => {
    speedRef.current = speedMultiplier;
  }, [speedMultiplier]);

  useEffect(() => {
    pausedRef.current = isPaused;
  }, [isPaused]);

  useEffect(() => {
    const trackElement = tickerTrackRef.current;
    if (!trackElement || tickerEntries.length === 0) {
      baseWidthRef.current = 0;
      offsetRef.current = 0;
      trackElement?.style && (trackElement.style.transform = '');
      return;
    }

    const computeBaseWidth = () => {
      const totalWidth = trackElement.scrollWidth;
      const nextBaseWidth = totalWidth > 0 ? totalWidth / 2 : 0;
      baseWidthRef.current = nextBaseWidth;

      if (nextBaseWidth > 0) {
        while (-offsetRef.current >= nextBaseWidth) {
          offsetRef.current += nextBaseWidth;
        }
      }

      trackElement.style.transform = `translateX(${offsetRef.current}px)`;
    };

    computeBaseWidth();

    let resizeObserver = null;
    const handleResize = () => computeBaseWidth();

    if (typeof ResizeObserver === 'function') {
      resizeObserver = new ResizeObserver(handleResize);
      resizeObserver.observe(trackElement);
      if (tickerViewportRef.current) {
        resizeObserver.observe(tickerViewportRef.current);
      }
    } else {
      window.addEventListener('resize', handleResize);
    }

    return () => {
      if (resizeObserver) {
        resizeObserver.disconnect();
      } else {
        window.removeEventListener('resize', handleResize);
      }
    };
  }, [tickerEntries]);

  useEffect(() => {
    const trackElement = tickerTrackRef.current;
    if (!trackElement || tickerEntries.length === 0) {
      if (trackElement) {
        trackElement.style.transform = '';
      }
      return;
    }

    offsetRef.current = 0;
    lastTimestampRef.current = null;
    trackElement.style.transform = 'translateX(0px)';

    const step = (timestamp) => {
      if (lastTimestampRef.current === null) {
        lastTimestampRef.current = timestamp;
      }
      const deltaSeconds = (timestamp - lastTimestampRef.current) / 1000;
      lastTimestampRef.current = timestamp;

      if (!pausedRef.current) {
        const speed = BASE_SCROLL_SPEED_PX * speedRef.current;
        const baseWidth = baseWidthRef.current;

        offsetRef.current -= speed * deltaSeconds;

        if (baseWidth > 0) {
          while (-offsetRef.current >= baseWidth) {
            offsetRef.current += baseWidth;
          }
        }
      }

      trackElement.style.transform = `translateX(${offsetRef.current}px)`;
      animationFrameRef.current = window.requestAnimationFrame(step);
    };

    animationFrameRef.current = window.requestAnimationFrame(step);

    return () => {
      if (animationFrameRef.current !== null) {
        window.cancelAnimationFrame(animationFrameRef.current);
        animationFrameRef.current = null;
      }
      lastTimestampRef.current = null;
    };
  }, [tickerEntries.length]);

  return (
    <div className="tab-content trajectory-ticker-tab">
      <div className="ticker-header">
        <h2>Trajectory Ticker</h2>
        <p>
          A continuous feed of the past three months of momentum and conviction deltas per technology. Drop this tab into an
          iframe for a stock-style crawl.
        </p>
      </div>
      <div className="ticker-body">
        {loading && <p className="ticker-status">Loading technologies...</p>}
        {!loading && error && <p className="ticker-status error">{error}</p>}
        {!loading && !error && tickerEntries.length === 0 && (
          <p className="ticker-status">No technologies meet the minimum data requirements yet.</p>
        )}
        {!loading && !error && tickerEntries.length > 0 && (
          <div
            className="ticker-viewport"
            aria-live="polite"
            ref={tickerViewportRef}
            onMouseEnter={() => setIsPaused(true)}
            onMouseLeave={() => setIsPaused(false)}
          >
            <div className="ticker-track" ref={tickerTrackRef}>
              {[...tickerEntries, ...tickerEntries].map((entry, index) => {
                const key = `${entry.techId}-${index >= tickerEntries.length ? 'dup' : 'base'}-${index}`;
                const deltaMomentumClass = entry.deltaMomentum >= 0 ? 'positive' : 'negative';
                const deltaConvictionClass = entry.deltaConviction >= 0 ? 'positive' : 'negative';

                return (
                  <div className="ticker-item" key={key}>
                    <span className="tech-name">{entry.techName}</span>
                    <span className={`delta ${deltaMomentumClass}`}>
                      Delta M {entry.deltaMomentum >= 0 ? '+' : ''}
                      {entry.deltaMomentum.toFixed(1)}
                    </span>
                    <span className={`delta ${deltaConvictionClass}`}>
                      Delta C {entry.deltaConviction >= 0 ? '+' : ''}
                      {entry.deltaConviction.toFixed(1)}
                    </span>
                    <span className={`badge ${entry.hasFullHistory ? 'success' : 'warning'}`}>
                      {entry.rangeLabel}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
      <div className="ticker-controls ticker-controls-footer">
        <label htmlFor="ticker-speed">Speed</label>
        <input
          id="ticker-speed"
          type="range"
          min="0.5"
          max="3"
          step="0.1"
          value={speedMultiplier}
          onChange={handleSpeedChange}
        />
        <span>{speedMultiplier.toFixed(1)}x</span>
      </div>
    </div>
  );
}

export default TrajectoryTickerTab;

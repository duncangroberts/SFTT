import React, { useEffect, useMemo, useState } from 'react';
import { collection, onSnapshot } from 'firebase/firestore';
import { db } from '../firebase';
import TrajectoryAnimationPlayer from './animations/TrajectoryAnimationPlayer';
import { computeTrajectoryDomains } from '../constants/trajectoryDomains';

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

function TrajectoryAnimationsTab() {
  const [rawData, setRawData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedTechId, setSelectedTechId] = useState(null);

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
        console.error('Error loading trajectory data:', err);
        setError('Unable to load trajectory data right now.');
        setLoading(false);
      }
    );

    return () => unsubscribe();
  }, []);

  const summaries = useMemo(() => buildTrajectorySummary(rawData), [rawData]);
  const domainConfig = useMemo(() => computeTrajectoryDomains(rawData), [rawData]);
  const momentumDomain = domainConfig.momentum;
  const convictionDomain = domainConfig.conviction;

  useEffect(() => {
    if (summaries.length === 0) {
      setSelectedTechId(null);
      return;
    }

    if (!selectedTechId || !summaries.some((summary) => summary.techId === selectedTechId)) {
      setSelectedTechId(summaries[0].techId);
    }
  }, [summaries, selectedTechId]);

  const selectedTech = summaries.find((summary) => summary.techId === selectedTechId) || null;
  return (
    <div className="tab-content trajectory-animation-tab">
      <aside className="trajectory-animation-sidebar">
        <div className="sidebar-header">
          <h2>Trajectory Animations</h2>
          <p>Select any technology to preview a three-month movement loop. Perfect for screen capture or drop-in video assets.</p>
        </div>
        <div className="sidebar-list">
          {loading && <p className="sidebar-status">Loading technologies...</p>}
          {error && <p className="sidebar-status error">{error}</p>}
          {!loading && !error && summaries.length === 0 && (
            <p className="sidebar-status">No technologies have the minimum data required just yet.</p>
          )}
          {!loading && !error && summaries.length > 0 && (
            <ul>
              {summaries.map((summary) => {
                const latestPoint = summary.points[summary.points.length - 1];
                const earliestPoint = summary.points[0];
                const deltaMomentum = latestPoint.momentum - earliestPoint.momentum;
                const deltaConviction = latestPoint.conviction - earliestPoint.conviction;

                return (
                  <li key={summary.techId}>
                    <button
                      type="button"
                      className={`trajectory-animation-item ${
                        selectedTechId === summary.techId ? 'active' : ''
                      }`}
                      onClick={() => setSelectedTechId(summary.techId)}
                    >
                      <div className="title-row">
                        <span className="title">{summary.techName}</span>
                        <span className={`badge ${summary.hasFullHistory ? 'success' : 'warning'}`}>
                          {summary.hasFullHistory ? '3 mo window' : `${summary.points.length} mo`}
                        </span>
                      </div>
                      <div className="meta-row">
                        <span className="range">
                          {formatMonth(earliestPoint.month)} -> {formatMonth(latestPoint.month)}
                        </span>
                        <span className={`delta ${deltaMomentum >= 0 ? 'positive' : 'negative'}`}>
                          Delta M {deltaMomentum.toFixed(1)}
                        </span>
                        <span className={`delta ${deltaConviction >= 0 ? 'positive' : 'negative'}`}>
                          Delta C {deltaConviction.toFixed(1)}
                        </span>
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </aside>
      <section className="trajectory-animation-main">
        {loading && <p className="main-status">Preparing animation canvas...</p>}
        {!loading && error && <p className="main-status error">{error}</p>}
        {!loading && !error && !selectedTech && (
          <div className="trajectory-animation-placeholder">
            <h3>Select a technology to get started</h3>
            <p>
              We&rsquo;ll render a dedicated animated quadrant showing how momentum and conviction scores evolve month by month
              for the chosen technology.
            </p>
          </div>
        )}
        {!loading && !error && selectedTech && (
          <TrajectoryAnimationPlayer
            key={selectedTech.techId}
            techName={selectedTech.techName}
            points={selectedTech.points}
            momentumDomain={momentumDomain}
            convictionDomain={convictionDomain}
          />
        )}
      </section>
    </div>
  );
}

export default TrajectoryAnimationsTab;

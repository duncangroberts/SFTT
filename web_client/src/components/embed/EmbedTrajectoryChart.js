import React, { useState, useEffect } from 'react';
import { db } from '../../firebase';
import { collection, onSnapshot } from 'firebase/firestore';
import TrajectoriesChart from '../charts/TrajectoriesChart';

function EmbedTrajectoryChart() {
  useEffect(() => {
    const root = document.documentElement;
    root.classList.add('embed-mode');
    document.body.classList.add('embed-mode');
    document.body.style.overflow = 'hidden';
    return () => {
      root.classList.remove('embed-mode');
      document.body.classList.remove('embed-mode');
      document.body.style.overflow = 'auto';
    };
  }, []);

  const [allData, setAllData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isMobile, setIsMobile] = useState(false);
  const [selectedTech, setSelectedTech] = useState(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setIsMobile(params.get('mobile') === 'true');
  }, []);

  useEffect(() => {
    const sentimentCollection = collection(db, 'monthly_sentiment');
    const unsubscribe = onSnapshot(sentimentCollection, (querySnapshot) => {
      const data = [];
      querySnapshot.forEach((doc) => {
        const docData = doc.data();
        const momentum = (Number(docData.average_tone) || 0) + (Number(docData.analyst_lit_score) || 0) + (Number(docData.analyst_whimsy_score) || 0);
        const conviction = (Number(docData.hn_avg_compound) || 0) + (Number(docData.analyst_lit_score) || 0) + (Number(docData.analyst_whimsy_score) || 0);
        data.push({ ...docData, momentum, conviction });
      });
      setAllData(data);
      setLoading(false);
    });

    return () => unsubscribe();
  }, []);

  const handleTechClick = (tech) => {
    setSelectedTech(tech);
  };

  const handleBackClick = () => {
    setSelectedTech(null);
  };

  const getLatestData = (data) => {
    const latestData = {};
    data.forEach(d => {
      if (!latestData[d.tech_id] || d.month > latestData[d.tech_id].month) {
        latestData[d.tech_id] = d;
      }
    });
    return Object.values(latestData);
  };

  if (isMobile) {
    if (selectedTech) {
      return (
        <div className="embed-container">
          <button onClick={handleBackClick}>&larr; Back to list</button>
          <TrajectoriesChart data={allData.filter(d => d.tech_id === selectedTech.tech_id)} fixedMonths={3} isMobile={true} />
        </div>
      );
    } else {
      return (
        <div className="embed-container tech-list-container">
          <h4>Technologies</h4>
          <ul className="tech-list">
            {getLatestData(allData).map(tech => (
              <li key={tech.tech_id} onClick={() => handleTechClick(tech)}>
                <strong>{tech.tech_name}</strong>
                <div>Momentum: {tech.momentum.toFixed(2)}</div>
                <div>Conviction: {tech.conviction.toFixed(2)}</div>
              </li>
            ))}
          </ul>
          <p className="desktop-notice">To view the full trajectory chart, please view on desktop.</p>
        </div>
      );
    }
  }

  // Desktop view
  return (
    <div className="embed-container">
      {loading ? (
        <p>Loading chart...</p>
      ) : allData.length > 0 ? (
        <TrajectoriesChart data={allData} fixedMonths={3} isMobile={isMobile} />
      ) : (
                <p>No data found.</p>
      )}
    </div>
  );
}

export default EmbedTrajectoryChart;


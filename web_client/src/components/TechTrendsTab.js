
import React, { useState, useEffect } from 'react';
import { db } from '../firebase';
import { collection, onSnapshot } from 'firebase/firestore';
import QuadrantPlot from './charts/QuadrantPlot';
import CommentVolumeChart from './charts/CommentVolumeChart';
import TrajectoriesChart from './charts/TrajectoriesChart';
import TrendsChart from './charts/TrendsChart';

const CHART_COMPONENTS = {
  quadrant: QuadrantPlot,
  volume: CommentVolumeChart,
  trajectories: TrajectoriesChart,
  trends: TrendsChart,
};

function TechTrendsTab() {
  const [allData, setAllData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeChart, setActiveChart] = useState('quadrant');

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
    }, (error) => {
      console.error("Error fetching sentiment data: ", error);
      setLoading(false);
    });

    return () => unsubscribe();
  }, []);

  const ActiveChartComponent = CHART_COMPONENTS[activeChart];

  return (
    <div className="tab-content">
      <div className="sub-nav">
        {Object.keys(CHART_COMPONENTS).map(key => (
          <button 
            key={key} 
            className={activeChart === key ? 'active' : ''}
            onClick={() => setActiveChart(key)}
          >
            {key.charAt(0).toUpperCase() + key.slice(1)}
          </button>
        ))}
      </div>
      <div className="chart-content-wrapper">
        {loading ? (
          <p>Loading data...</p>
        ) : allData.length > 0 ? (
          <ActiveChartComponent data={allData} />
        ) : (
          <p>No data found in the database.</p>
        )}
      </div>
    </div>
  );
}

export default TechTrendsTab;

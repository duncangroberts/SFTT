import React, { useState, useEffect } from 'react';
import { db } from '../../firebase';
import { collection, onSnapshot } from 'firebase/firestore';
import TrajectoriesChart from '../charts/TrajectoriesChart';

function EmbedTrajectoryChart() {
  useEffect(() => {
    const root = document.documentElement;
    root.classList.add('embed-mode');
    document.body.classList.add('embed-mode');
    return () => {
      root.classList.remove('embed-mode');
      document.body.classList.remove('embed-mode');
    };
  }, []);
  const [allData, setAllData] = useState([]);
  const [loading, setLoading] = useState(true);

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

  return (
    <div className="embed-container">
      {loading ? (
        <p>Loading chart...</p>
      ) : allData.length > 0 ? (
        <TrajectoriesChart data={allData} fixedMonths={3} />
      ) : (
        <p>No data found.</p>
      )}
    </div>
  );
}

export default EmbedTrajectoryChart;


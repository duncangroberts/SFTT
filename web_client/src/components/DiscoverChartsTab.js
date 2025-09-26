
import React, { useState, useEffect } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell, ReferenceLine } from 'recharts';
import { db } from '../firebase';
import { collection, onSnapshot, query, orderBy, limit } from 'firebase/firestore';

function DiscoverChartsTab() {
  const [themes, setThemes] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const themesCollection = collection(db, 'themes');
    const q = query(themesCollection, orderBy('discussion_score', 'desc'), limit(10));

    const unsubscribe = onSnapshot(q, (querySnapshot) => {
      const themesData = [];
      querySnapshot.forEach((doc) => {
        themesData.push({ id: doc.id, ...doc.data() });
      });
      setThemes(themesData);
      setLoading(false);
    });

    return () => unsubscribe();
  }, []);

  const discussionData = [...themes].sort((a, b) => a.discussion_score - b.discussion_score);
  const sentimentData = [...themes].sort((a, b) => a.sentiment_score - b.sentiment_score);

  return (
    <div className="tab-content">
      {loading ? (
        <p>Loading charts...</p>
      ) : themes.length > 0 ? (
        <div className="charts-wrapper">
          <div className="chart-container">
            <h4>Top Themes by Discussion Score</h4>
            <BarChart
              width={800}
              height={500}
              data={discussionData}
              layout="vertical"
              margin={{ top: 5, right: 30, left: 150, bottom: 5 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#444" />
              <XAxis type="number" stroke="#aaa" tick={false} />
              <YAxis type="category" dataKey="name" stroke="#aaa" width={150} />
              <Tooltip />
              <Bar dataKey="discussion_score" fill="#3ab4f2" />
            </BarChart>
          </div>
          <div className="chart-container">
            <h4>Top Themes by Sentiment</h4>
            <BarChart
              width={800}
              height={500}
              data={sentimentData}
              layout="vertical"
              margin={{ top: 5, right: 30, left: 150, bottom: 5 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#444" />
              <XAxis type="number" stroke="#aaa" domain={[-1, 1]} tick={false} />
              <YAxis type="category" dataKey="name" stroke="#aaa" width={150} />
              <Tooltip />
              <ReferenceLine x={0} stroke="#888" />
              <Bar dataKey="sentiment_score">
                {sentimentData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.sentiment_score < 0 ? '#f2545b' : '#5ad1a4'} />
                ))}
              </Bar>
            </BarChart>
          </div>
        </div>
      ) : (
        <p>No theme data to display.</p>
      )}
    </div>
  );
}

export default DiscoverChartsTab;

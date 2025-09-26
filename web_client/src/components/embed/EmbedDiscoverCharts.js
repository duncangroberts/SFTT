import React, { useState, useEffect } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell, ReferenceLine, ResponsiveContainer } from 'recharts';
import { db } from '../../firebase';
import { collection, onSnapshot, query, orderBy, limit } from 'firebase/firestore';

function EmbedDiscoverCharts() {
  useEffect(() => {
    const root = document.documentElement;
    root.classList.add('embed-mode');
    document.body.classList.add('embed-mode');
    return () => {
      root.classList.remove('embed-mode');
      document.body.classList.remove('embed-mode');
    };
  }, []);
  const [themes, setThemes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isSmallScreen, setIsSmallScreen] = useState(false);

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

  useEffect(() => {
    const updateScreenSize = () => setIsSmallScreen(window.innerWidth < 900);
    updateScreenSize();
    window.addEventListener('resize', updateScreenSize);
    return () => window.removeEventListener('resize', updateScreenSize);
  }, []);

  const discussionData = [...themes].sort((a, b) => a.discussion_score - b.discussion_score);
  const sentimentData = [...themes].sort((a, b) => a.sentiment_score - b.sentiment_score);
  const chartHeight = isSmallScreen ? 360 : 480;
  const yAxisWidth = isSmallScreen ? 110 : 150;

  return (
    <div className="embed-container">
      {loading ? (
        <p>Loading charts...</p>
      ) : themes.length > 0 ? (
        <div className="charts-wrapper">
          <div className="chart-container">
            <h4>Top Themes by Sentiment</h4>
            <ResponsiveContainer width="100%" height={chartHeight}>
              <BarChart
                data={sentimentData}
                layout="vertical"
                margin={{ top: 5, right: 20, left: yAxisWidth, bottom: 5 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#444" />
                <XAxis type="number" domain={[-1, 1]} tick={{ fill: "#ddd" }} axisLine={{ stroke: "#666" }} tickLine={false} />
                <YAxis type="category" dataKey="name" width={yAxisWidth} tick={{ fill: "#ddd" }} axisLine={{ stroke: "#666" }} tickLine={false} />
                <Tooltip contentStyle={{ backgroundColor: "#111", border: "1px solid #444", color: "#fff" }} cursor={{ fill: "rgba(255,255,255,0.05)" }} />
                <ReferenceLine x={0} stroke="#888" />
                <Bar dataKey="sentiment_score">
                  {sentimentData.map((entry, index) => (
                    <Cell key={`sentiment-${entry.id ?? index}`} fill={entry.sentiment_score < 0 ? '#f2545b' : '#5ad1a4'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="chart-container">
            <h4>Top Themes by Discussion Score</h4>
            <ResponsiveContainer width="100%" height={chartHeight}>
              <BarChart
                data={discussionData}
                layout="vertical"
                margin={{ top: 5, right: 20, left: yAxisWidth, bottom: 5 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#444" />
                <XAxis type="number" tick={{ fill: "#ddd" }} axisLine={{ stroke: "#666" }} tickLine={false} />
                <YAxis type="category" dataKey="name" width={yAxisWidth} tick={{ fill: "#ddd" }} axisLine={{ stroke: "#666" }} tickLine={false} />
                <Tooltip contentStyle={{ backgroundColor: "#111", border: "1px solid #444", color: "#fff" }} cursor={{ fill: "rgba(255,255,255,0.05)" }} />
                <Bar dataKey="discussion_score" fill="#3ab4f2" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      ) : (
        <p>No theme data to display.</p>
      )}
    </div>
  );
}

export default EmbedDiscoverCharts;


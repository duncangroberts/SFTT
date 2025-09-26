
import React, { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from 'recharts';

const COLORS = ['#ff6b35', '#f7c843', '#3ab4f2', '#f2545b', '#b353ff', '#5ad1a4'];

function TrendsChart({ data, width, height }) {
  const [numMonths, setNumMonths] = useState(12);
  const [chartData, setChartData] = useState([]);
  const [series, setSeries] = useState([]);

  useEffect(() => {
    if (!data || data.length === 0) {
        setChartData([]);
        setSeries([]);
        return;
    }

    const allMonths = [...new Set(data.map(d => d.month))].sort().reverse();
    const relevantMonths = allMonths.slice(0, numMonths).sort();

    const techSeries = [...new Set(data.map(d => d.tech_name))];

    const trendsData = relevantMonths.map(month => {
      const monthData = { month };
      techSeries.forEach(techName => {
        const dataPoint = data.find(d => d.month === month && d.tech_name === techName);
        monthData[techName] = dataPoint ? dataPoint.momentum : null;
      });
      return monthData;
    });

    setChartData(trendsData);
    setSeries(techSeries);

  }, [data, numMonths]);

  return (
    <div className="chart-container">
      <h4>Momentum Trends</h4>
      <div className="controls">
        <label>Months of History: </label>
        <select value={numMonths} onChange={e => setNumMonths(parseInt(e.target.value, 10))}>
          {[3, 6, 9, 12, 24, 36].map(m => <option key={m} value={m}>{m}</option>)}
        </select>
      </div>
      {chartData.length > 0 ? (
        <LineChart
          width={width}
          height={height}
          data={chartData}
          margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#444" />
          <XAxis dataKey="month" stroke="#aaa" />
          <YAxis stroke="#aaa" />
          <Tooltip />
          <Legend />
          {series.map((techName, index) => (
            <Line key={techName} type="monotone" dataKey={techName} stroke={COLORS[index % COLORS.length]} connectNulls />
          ))}
        </LineChart>
      ) : <p>No data for this time range.</p>}
    </div>
  );
}

export default TrendsChart;

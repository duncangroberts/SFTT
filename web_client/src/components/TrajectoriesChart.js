
import React, { useState, useEffect } from 'react';
import { ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from 'recharts';

const COLORS = ['#ff6b35', '#f7c843', '#3ab4f2', '#f2545b', '#b353ff', '#5ad1a4'];

function TrajectoriesChart({ data, width, height }) {
  const [numMonths, setNumMonths] = useState(6);
  const [chartData, setChartData] = useState([]);

  useEffect(() => {
    if (!data || data.length === 0) {
      setChartData([]);
      return;
    }

    const allMonths = [...new Set(data.map(d => d.month))].sort().reverse();
    const relevantMonths = allMonths.slice(0, numMonths);
    
    const filtered = data.filter(d => relevantMonths.includes(d.month));

    const trajectories = filtered.reduce((acc, d) => {
      if (!d.tech_id) return acc;
      if (!acc[d.tech_id]) {
        acc[d.tech_id] = { name: d.tech_name, data: [] };
      }
      acc[d.tech_id].data.push({ month: d.month, momentum: d.momentum, conviction: d.conviction });
      return acc;
    }, {});

    Object.values(trajectories).forEach(t => t.data.sort((a, b) => a.month.localeCompare(b.month)));
    setChartData(Object.values(trajectories));

  }, [data, numMonths]);

  return (
    <div className="chart-container">
      <h4>Trajectories</h4>
      <div className="controls">
        <label>Months of History: </label>
        <select value={numMonths} onChange={e => setNumMonths(parseInt(e.target.value, 10))}>
          {[3, 6, 9, 12, 24].map(m => <option key={m} value={m}>{m}</option>)}
        </select>
      </div>
      {chartData.length > 0 ? (
        <ScatterChart
          width={width}
          height={height}
          margin={{ top: 20, right: 20, bottom: 20, left: 20 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#444" />
          <XAxis type="number" dataKey="momentum" name="Momentum" stroke="#aaa" domain={['dataMin - 1', 'dataMax + 1']} />
          <YAxis type="number" dataKey="conviction" name="Conviction" stroke="#aaa" domain={['dataMin - 1', 'dataMax + 1']} />
          <Tooltip cursor={{ strokeDasharray: '3 3' }} />
          <Legend />
          {chartData.map((s, index) => (
            <Scatter key={s.name} name={s.name} data={s.data} fill={COLORS[index % COLORS.length]} line shape="circle" />
          ))}
        </ScatterChart>
      ) : <p>No data for this time range.</p>}
    </div>
  );
}

export default TrajectoriesChart;

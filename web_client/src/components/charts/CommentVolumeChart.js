
import React, { useState, useEffect } from 'react';
import { PieChart, Pie, Cell, Tooltip, Legend } from 'recharts';

const COLORS = ['#ff6b35', '#f7c843', '#3ab4f2', '#f2545b', '#b353ff', '#5ad1a4'];

function CommentVolumeChart({ data }) {
  const [filteredData, setFilteredData] = useState([]);
  const [months, setMonths] = useState([]);
  const [selectedMonth, setSelectedMonth] = useState('');

  useEffect(() => {
    if (data && data.length > 0) {
      const monthSet = new Set(data.map(d => d.month));
      const sortedMonths = Array.from(monthSet).sort().reverse();
      setMonths(sortedMonths);
      if (sortedMonths.length > 0) {
        setSelectedMonth(sortedMonths[0]);
      }
    }
  }, [data]);

  useEffect(() => {
    if (selectedMonth) {
      const monthData = data.filter(d => d.month === selectedMonth);
      setFilteredData(monthData);
    }
  }, [selectedMonth, data]);

  const chartData = filteredData.filter(d => d.hn_comment_count > 0).map(d => ({
    name: d.tech_name,
    value: d.hn_comment_count
  }));

  return (
    <div className="chart-container full-width">
      <div className="controls">
        <label htmlFor="month-select">Select Month: </label>
        <select id="month-select" value={selectedMonth} onChange={e => setSelectedMonth(e.target.value)}>
          {months.map(m => <option key={m} value={m}>{m}</option>)}
        </select>
      </div>
      {chartData.length > 0 ? (
        <PieChart width={1100} height={700}>
          <Pie
            data={chartData}
            cx={550}
            cy={350}
            labelLine={false}
            outerRadius={250}
            fill="#8884d8"
            dataKey="value"
            label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
          >
            {chartData.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip />
          <Legend wrapperStyle={{bottom: 30}}/>
        </PieChart>
      ) : <p>No comment data for this month.</p>}
    </div>
  );
}

export default CommentVolumeChart;

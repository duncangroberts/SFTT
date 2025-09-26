import React from 'react';
import { PieChart, Pie, Cell, Tooltip, Legend } from 'recharts';

const COLORS = ['#ff6b35', '#f7c843', '#3ab4f2', '#f2545b', '#b353ff', '#5ad1a4'];

const CustomTooltip = ({ active, payload }) => {
  if (active && payload && payload.length) {
    return (
      <div className="custom-tooltip">
        <p className="label">{`${payload[0].name} : ${payload[0].value}`}</p>
      </div>
    );
  }
  return null;
};

function CommentVolumeChart({ data, width, height }) {
  const chartData = data.filter(d => d.hn_comment_count > 0).map(d => ({
    name: d.tech_name,
    value: d.hn_comment_count
  }));

  if (chartData.length === 0) {
    return (
        <div className="chart-container" style={{width: width, height: height}}>
            <h4>Hacker News Comment Volume</h4>
            <p>No comment data for this month.</p>
        </div>
    );
  }

  return (
    <div className="chart-container">
      <h4>Hacker News Comment Volume</h4>
      <PieChart width={width} height={height}>
        <Pie
          data={chartData}
          cx={width / 2}
          cy={height / 2 - 20}
          labelLine={false}
          outerRadius={Math.min(width, height) / 4}
          fill="#8884d8"
          dataKey="value"
        >
          {chartData.map((entry, index) => (
            <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
          ))}
        </Pie>
        <Tooltip content={<CustomTooltip />} />
        <Legend wrapperStyle={{bottom: 0}} />
      </PieChart>
    </div>
  );
}

export default CommentVolumeChart;
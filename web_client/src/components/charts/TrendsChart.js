import React, { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Label, LabelList } from 'recharts';
import { getColor } from '../../utils/colorHelper';

function TrendsChart({ data }) {
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

  const CustomizedLabel = ({ x, y, stroke, value, index, dataKey }) => {
    if (index === chartData.length - 1) {
      return (
        <text x={x} y={y} dy={-4} fill={stroke} fontSize={12} textAnchor="middle">
          {dataKey}
        </text>
      );
    }
    return null;
  };

  return (
    <div className="chart-container full-width">
      <div className="controls">
        <label>Months of History: </label>
        <select value={numMonths} onChange={e => setNumMonths(parseInt(e.target.value, 10))}>
          {[3, 6, 9, 12, 24, 36].map(m => <option key={m} value={m}>{m}</option>)}
        </select>
      </div>
      {chartData.length > 0 ? (
        <LineChart
          width={1100}
          height={700}
          data={chartData}
          margin={{ top: 20, right: 100, left: 40, bottom: 20 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#444" />
          <XAxis dataKey="month" stroke="#aaa" />
          <YAxis stroke="#aaa" tick={false}>
            <Label value="Momentum" angle={-90} offset={-20} position="insideLeft" fill="#aaa" />
          </YAxis>
          <Tooltip />
          {series.map((techName, index) => (
            <Line key={techName} type="monotone" dataKey={techName} stroke={getColor(techName)} connectNulls dot={false}>
                <LabelList dataKey={techName} content={<CustomizedLabel />} />
            </Line>
          ))}
        </LineChart>
      ) : <p>No data for this time range.</p>}
    </div>
  );
}

export default TrendsChart;
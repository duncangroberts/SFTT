
import React, { useState, useEffect } from 'react';
import { ScatterChart, Scatter, XAxis, YAxis, Tooltip, ReferenceLine, Label, LabelList, Cell } from 'recharts';
import { getColor } from '../../utils/colorHelper';

function QuadrantPlot({ data }) {
  const [filteredData, setFilteredData] = useState([]);
  const [months, setMonths] = useState([]);
  const [selectedMonth, setSelectedMonth] = useState('');
  const [xDomain, setXDomain] = useState(['auto', 'auto']);
  const [yDomain, setYDomain] = useState(['auto', 'auto']);

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

      if (monthData.length > 0) {
        const allMomentum = monthData.map(d => d.momentum);
        const allConviction = monthData.map(d => d.conviction);
        const xMin = Math.min(...allMomentum);
        const xMax = Math.max(...allMomentum);
        const yMin = Math.min(...allConviction);
        const yMax = Math.max(...allConviction);
        const xPad = (xMax - xMin) * 0.1 || 1;
        const yPad = (yMax - yMin) * 0.1 || 1;
        setXDomain([xMin - xPad, xMax + xPad]);
        setYDomain([yMin - yPad, yMax + yPad]);
      }
    }
  }, [selectedMonth, data]);

  const midX = xDomain[0] + (xDomain[1] - xDomain[0]) / 2;
  const midY = yDomain[0] + (yDomain[1] - yDomain[0]) / 2;

  return (
    <div className="chart-container full-width">
      <div className="controls">
        <label htmlFor="month-select">Select Month: </label>
        <select id="month-select" value={selectedMonth} onChange={e => setSelectedMonth(e.target.value)}>
          {months.map(m => <option key={m} value={m}>{m}</option>)}
        </select>
      </div>
      {filteredData.length > 0 ? (
        <ScatterChart
          width={1100}
          height={700}
          margin={{ top: 20, right: 120, bottom: 40, left: 40 }}
        >
          <XAxis type="number" dataKey="momentum" name="Momentum" stroke="#aaa" domain={xDomain} tick={false}>
            <Label value="Momentum" offset={-25} position="insideBottom" fill="#aaa" />
          </XAxis>
          <YAxis type="number" dataKey="conviction" name="Conviction" stroke="#aaa" domain={yDomain} tick={false}>
            <Label value="Conviction" angle={-90} offset={-20} position="insideLeft" fill="#aaa" />
          </YAxis>
          <Tooltip cursor={{ strokeDasharray: '3 3' }} />
          <Scatter name="Technologies" data={filteredData}>
            <LabelList dataKey="tech_name" position="right" style={{ fontSize: 12 }} />
            {filteredData.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={getColor(entry.tech_name)} />
            ))}
          </Scatter>
          <ReferenceLine y={midY} stroke="#aaa" strokeDasharray="2 2" />
          <ReferenceLine x={midX} stroke="#aaa" strokeDasharray="2 2" />
        </ScatterChart>
      ) : <p>No data for this month.</p>}
    </div>
  );
}

export default QuadrantPlot;

import React, { useState, useEffect } from 'react';
import { ScatterChart, Scatter, XAxis, YAxis, ZAxis, ReferenceLine, Label, LabelList, ResponsiveContainer } from 'recharts';
import { getColor } from '../../utils/colorHelper';

const CustomizedLabel = ({ x, y, value }) => (
  <text x={x} y={y} dy={-10} fontSize={12} textAnchor="middle" fill="#fff">
    {value}
  </text>
);

function TrajectoriesChart({ data, fixedMonths = null }) {
  const [numMonths, setNumMonths] = useState(fixedMonths || 6);
  const [chartData, setChartData] = useState([]);
  const [xDomain, setXDomain] = useState(['auto', 'auto']);
  const [yDomain, setYDomain] = useState(['auto', 'auto']);
  const [isSmallScreen, setIsSmallScreen] = useState(false);

  useEffect(() => {
    const updateScreenSize = () => setIsSmallScreen(window.innerWidth < 768);
    updateScreenSize();
    window.addEventListener('resize', updateScreenSize);
    return () => window.removeEventListener('resize', updateScreenSize);
  }, []);

  useEffect(() => {
    if (!data || data.length === 0) {
      setChartData([]);
      return;
    }

    const allMonths = [...new Set(data.map(d => d.month))].sort().reverse();
    const relevantMonths = allMonths.slice(0, numMonths);
    
    const filtered = data.filter(d => relevantMonths.includes(d.month));

    if (filtered.length === 0) {
      setChartData([]);
      return;
    }

    const trajectories = filtered.reduce((acc, d) => {
      if (!d.tech_id) return acc;
      if (!acc[d.tech_id]) {
        acc[d.tech_id] = { name: d.tech_name, data: [] };
      }
      acc[d.tech_id].data.push({ month: d.month, momentum: d.momentum, conviction: d.conviction });
      return acc;
    }, {});

    Object.values(trajectories).forEach(t => {
      t.data.sort((a, b) => a.month.localeCompare(b.month));
      const pointCount = t.data.length;
      t.data.forEach((point, index) => {
        const frac = pointCount > 1 ? index / (pointCount - 1) : 1;
        point.size = 30 + (150 - 30) * frac;
        if (index === pointCount - 1) {
          point.label = t.name;
        }
      });
    });

    setChartData(Object.values(trajectories));

    const allMomentum = filtered.map(d => d.momentum);
    const allConviction = filtered.map(d => d.conviction);
    const xMin = Math.min(...allMomentum);
    const xMax = Math.max(...allMomentum);
    const yMin = Math.min(...allConviction);
    const yMax = Math.max(...allConviction);
    const xPad = (xMax - xMin) * 0.2 || 1;
    const yPad = (yMax - yMin) * 0.2 || 1;
    setXDomain([xMin - xPad, xMax + xPad]);
    setYDomain([yMin - yPad, yMax + yPad]);

  }, [data, numMonths]);

  const midX = xDomain[0] + (xDomain[1] - xDomain[0]) / 2;
  const midY = yDomain[0] + (yDomain[1] - yDomain[0]) / 2;
  const chartHeight = isSmallScreen ? 320 : 520;
  const chartMargin = isSmallScreen ? { top: 10, right: 30, bottom: 40, left: 30 } : { top: 20, right: 40, bottom: 60, left: 40 };

  return (
    <div className="chart-container full-width">
      {!fixedMonths && (
        <div className="controls">
          <label>Months of History: </label>
          <select value={numMonths} onChange={e => setNumMonths(parseInt(e.target.value, 10))}>
            {[3, 6, 9, 12, 24].map(m => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>
      )}
      {chartData.length > 0 ? (
        <ResponsiveContainer width="100%" height={chartHeight}>
          <ScatterChart margin={chartMargin}>
            <ZAxis dataKey="size" range={[20, 250]} />
            <XAxis type="number" dataKey="momentum" name="Momentum" domain={xDomain} tick={false} axisLine={{ stroke: "#666" }} tickLine={false}>
              <Label value="Momentum" offset={-25} position="insideBottom" fill="#fff" />
            </XAxis>
            <YAxis type="number" dataKey="conviction" name="Conviction" domain={yDomain} tick={false} axisLine={{ stroke: "#666" }} tickLine={false}>
              <Label value="Conviction" angle={-90} offset={-20} position="insideLeft" fill="#fff" />
            </YAxis>
            {chartData.map((s) => (
              <Scatter key={s.name} name={s.name} data={s.data} fill={getColor(s.name)} line={{ strokeOpacity: 0.5, strokeWidth: 2}} shape="circle">
                <LabelList dataKey="label" content={<CustomizedLabel />} />
              </Scatter>
            ))}
            <ReferenceLine y={midY} stroke="#555" strokeDasharray="3 3" />
            <ReferenceLine x={midX} stroke="#555" strokeDasharray="3 3" />
          </ScatterChart>
        </ResponsiveContainer>
      ) : <p>No data for this time range.</p>}
    </div>
  );
}

export default TrajectoriesChart;











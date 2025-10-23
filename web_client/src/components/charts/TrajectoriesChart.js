import React, { useState, useEffect, useMemo } from 'react';
import { ScatterChart, Scatter, XAxis, YAxis, ZAxis, ReferenceLine, Label, ResponsiveContainer, Tooltip } from 'recharts';
import { getColor } from '../../utils/colorHelper';
import { computeTrajectoryDomains } from '../../constants/trajectoryDomains';

const CustomLegend = ({ data }) => {
  return (
    <div className="custom-legend">
      {data.map(item => (
        <div key={item.name} className="legend-item">
          <div className="legend-color" style={{ backgroundColor: getColor(item.name) }}></div>
          <div className="legend-label">{item.name}</div>
        </div>
      ))}
    </div>
  );
};

function TrajectoriesChart({ data, fixedMonths = null, isMobile = false }) {
  const [numMonths, setNumMonths] = useState(fixedMonths || 6);
  const [chartData, setChartData] = useState([]);
  const [isSmallScreen, setIsSmallScreen] = useState(false);
  const [hoveredPoint, setHoveredPoint] = useState(null);

  useEffect(() => {
    const updateScreenSize = () => setIsSmallScreen(window.innerWidth < 768);
    updateScreenSize();
    window.addEventListener('resize', updateScreenSize);
    return () => window.removeEventListener('resize', updateScreenSize);
  }, []);

  useEffect(() => {
    if (!data || data.length === 0) {
      setChartData([]);
      setHoveredPoint(null);
      return;
    }

    const allMonths = [...new Set(data.map(d => d.month))].sort().reverse();
    const relevantMonths = allMonths.slice(0, numMonths);
    
    const filtered = data.filter(d => relevantMonths.includes(d.month));

    if (filtered.length === 0) {
      setChartData([]);
      setHoveredPoint(null);
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

    const newChartData = Object.values(trajectories).map(t => {
      const sortedData = [...t.data].sort((a, b) => a.month.localeCompare(b.month));
      const pointCount = sortedData.length;
      const newData = sortedData.map((point, index) => {
        const frac = pointCount > 1 ? index / (pointCount - 1) : 1;
        return {
          ...point,
          techName: t.name,
          size: 30 + (150 - 30) * frac,
        };
      });
      return { ...t, data: newData };
    });

    setChartData(newChartData);
    setHoveredPoint(null);

  }, [data, numMonths]);

  const CustomTooltip = ({ active }) => {
    if (!active || !hoveredPoint) {
      return null;
    }

    const techLabel = hoveredPoint.techName || hoveredPoint.tech_name || hoveredPoint.seriesName || hoveredPoint.name;

    if (!techLabel) {
      return null;
    }

    return (
      <div className="custom-tooltip" style={{ backgroundColor: 'rgba(0, 0, 0, 0.8)', padding: '10px', border: '1px solid #ccc', borderRadius: '5px' }}>
        <p style={{ color: '#fff', margin: 0 }}>{techLabel}</p>
      </div>
    );
  };

  const domainConfig = useMemo(() => computeTrajectoryDomains(data), [data]);

  const xDomain = domainConfig.momentum;
  const yDomain = domainConfig.conviction;
  const midX = domainConfig.midMomentum;
  const midY = domainConfig.midConviction;
  const chartHeight = (isSmallScreen || isMobile) ? 320 : 820;
  const chartMargin = (isSmallScreen || isMobile) ? { top: 10, right: 30, bottom: 60, left: 30 } : { top: 20, right: 40, bottom: 80, left: 40 };

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
            <Tooltip content={<CustomTooltip />} cursor={{ strokeDasharray: '3 3' }} />
            <ZAxis dataKey="size" range={[20, 250]} />
            <XAxis type="number" dataKey="momentum" name="Momentum" domain={xDomain} tick={false} axisLine={{ stroke: "#666" }} tickLine={false}>
              <Label value="Momentum" offset={-25} position="insideBottom" fill="#fff" />
            </XAxis>
            <YAxis type="number" dataKey="conviction" name="Conviction" domain={yDomain} tick={false} axisLine={{ stroke: "#666" }} tickLine={false}>
              <Label value="Conviction" angle={-90} offset={-20} position="insideLeft" fill="#fff" />
            </YAxis>
            {chartData.map((s) => (
              <Scatter
                key={s.name}
                name={s.name}
                data={s.data}
                fill={getColor(s.name)}
                line={{ strokeOpacity: 0.5, strokeWidth: 2}}
                shape="circle"
                onMouseEnter={(point) => {
                  const dataPoint = point && point.payload ? point.payload : point;
                  setHoveredPoint({ ...dataPoint, seriesName: s.name });
                }}
                onMouseLeave={() => setHoveredPoint(null)}
              />
            ))}
            <ReferenceLine y={midY} stroke="#555" strokeDasharray="3 3" />
            <ReferenceLine x={midX} stroke="#555" strokeDasharray="3 3" />

            {/* Quadrant Labels */}
            <Label value="Momentum Zone" position="insideTopRight" offset={10} fill="#aaa" style={{ fontSize: '14px' }} />
            <Label value="Hype Trap" position="insideBottomRight" offset={10} fill="#aaa" style={{ fontSize: '14px' }} />
            <Label value="Hidden Gems" position="insideTopLeft" offset={10} fill="#aaa" style={{ fontSize: '14px' }} />
            <Label value="Sceptics' Corner" position="insideBottomLeft" offset={10} fill="#aaa" style={{ fontSize: '14px' }} />

          </ScatterChart>
        </ResponsiveContainer>
      ) : <p>No data for this time range.</p>}
      {chartData.length > 0 && <CustomLegend data={chartData} />}
    </div>
  );
}

export default TrajectoriesChart;







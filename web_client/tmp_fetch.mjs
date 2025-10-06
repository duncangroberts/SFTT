const res = await fetch('https://firestore.googleapis.com/v1/projects/sftt-3626f/databases/(default)/documents/monthly_sentiment?pageSize=200');
const json = await res.json();
const docs = json.documents || [];
const data = docs.map(doc => {
  const f = doc.fields;
  const getVal = (field) => {
    if (!field) return null;
    if ('doubleValue' in field) return Number(field.doubleValue);
    if ('integerValue' in field) return Number(field.integerValue);
    if ('stringValue' in field) return field.stringValue;
    return null;
  };
  return {
    tech_id: getVal(f.tech_id),
    tech_name: getVal(f.tech_name),
    month: getVal(f.month),
    average_tone: getVal(f.average_tone),
    hn_avg_compound: getVal(f.hn_avg_compound),
    analyst_lit_score: getVal(f.analyst_lit_score),
    analyst_whimsy_score: getVal(f.analyst_whimsy_score),
  };
});

const withScores = data.map(docData => {
  const momentum = (Number(docData.average_tone) || 0) + (Number(docData.analyst_lit_score) || 0) + (Number(docData.analyst_whimsy_score) || 0);
  const conviction = (Number(docData.hn_avg_compound) || 0) + (Number(docData.analyst_lit_score) || 0) + (Number(docData.analyst_whimsy_score) || 0);
  return { ...docData, momentum, conviction };
});

const numMonths = 6;
const allMonths = [...new Set(withScores.map(d => d.month))].sort().reverse();
const relevantMonths = allMonths.slice(0, numMonths);
const filtered = withScores.filter(d => relevantMonths.includes(d.month));
const trajectories = filtered.reduce((acc, d) => {
  if (!d.tech_id) return acc;
  if (!acc[d.tech_id]) {
    acc[d.tech_id] = { name: d.tech_name, data: [] };
  }
  acc[d.tech_id].data.push({ month: d.month, momentum: d.momentum, conviction: d.conviction });
  return acc;
}, {});

const chartData = Object.values(trajectories).map(t => {
  const sortedData = [...t.data].sort((a, b) => a.month.localeCompare(b.month));
  const newData = sortedData.map((point, index) => {
    const pointCount = t.data.length;
    const frac = pointCount > 1 ? index / (pointCount - 1) : 1;
    return { ...point, size: 30 + (150 - 30) * frac };
  });
  return { ...t, data: newData };
});

console.log(chartData.map(item => ({ name: item.name, points: item.data.length }))); 

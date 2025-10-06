from pathlib import Path
path = Path(r"src/components/charts/TrajectoriesChart.js")
text = path.read_text()
old_tooltip = """const CustomTooltip = ({ active, payload }) => {\n  if (active && payload && payload.length) {\n    const data = payload[0].payload;\n    const name = payload[0].name;\n    return (\n      <div className=\"custom-tooltip\">\n        <p className=\"label\">{name}</p>\n        <p className=\"intro\">{`Momentum: ${typeof data.momentum === 'number' ? data.momentum.toFixed(2) : 'N/A'}`}</p>\n        <p className=\"intro\">{`Conviction: ${typeof data.conviction === 'number' ? data.conviction.toFixed(2) : 'N/A'}`}</p>\n      </div>\n    );\n  }\n  return null;\n};\n"""
new_tooltip = """const CustomTooltip = ({ active, payload }) => {\n  if (active && payload && payload.length) {\n    const hovered = payload.find(item => item?.payload?.techName) ?? payload[0];\n    if (!hovered) {\n      return null;\n    }\n    const data = hovered.payload || {};\n    const name = data.techName || hovered.name;\n    return (\n      <div className=\"custom-tooltip\">\n        <p className=\"label\">{name}</p>\n        <p className=\"intro\">{`Momentum: ${typeof data.momentum === 'number' ? data.momentum.toFixed(2) : 'N/A'}`}</p>\n        <p className=\"intro\">{`Conviction: ${typeof data.conviction === 'number' ? data.conviction.toFixed(2) : 'N/A'}`}</p>\n      </div>\n    );\n  }\n  return null;\n};\n"""
if old_tooltip not in text:
    raise SystemExit('Original tooltip block not found')
text = text.replace(old_tooltip, new_tooltip)
old_newdata = """      const newData = sortedData.map((point, index) => {\n        const pointCount = t.data.length;\n        const frac = pointCount > 1 ? index / (pointCount - 1) : 1;\n        return {\n          ...point,\n          size: 30 + (150 - 30) * frac,\n        };\n      });\n      return { ...t, data: newData };\n    });\n"""
new_newdata = """      const newData = sortedData.map((point, index) => {\n        const pointCount = t.data.length;\n        const frac = pointCount > 1 ? index / (pointCount - 1) : 1;\n        return {\n          ...point,\n          techName: t.name,\n          size: 30 + (150 - 30) * frac,\n        };\n      });\n      return { ...t, data: newData };\n    });\n"""
if old_newdata not in text:
    raise SystemExit('Data transformation block not found')
text = text.replace(old_newdata, new_newdata)
path.write_text(text)

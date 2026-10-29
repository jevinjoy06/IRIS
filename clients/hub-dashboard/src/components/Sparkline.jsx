// Thin line trace of recent history. 2px line, rounded ends anchored to the
// baseline, a faint fill anchored at 0 (never a gradient used as pure decor —
// it reads the same magnitude the line already encodes, at low opacity).
export default function Sparkline({ data = [], max = 100, color = '#4ee6b8', height = 40 }) {
  const width = 160
  if (data.length < 2) {
    return <svg width={width} height={height} />
  }
  const step = width / (data.length - 1)
  const points = data.map((v, i) => {
    const x = i * step
    const y = height - (Math.max(0, Math.min(max, v)) / max) * height
    return [x, y]
  })
  const linePath = points.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
  const fillPath = `${linePath} L${width},${height} L0,${height} Z`

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      <path d={fillPath} fill={color} opacity={0.12} stroke="none" />
      <path d={linePath} fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

// Single-value radial gauge. Status color is driven purely by thresholds on
// the value itself (nominal/elevated/critical) — never decorative; phosphor
// means "reading live and normal," amber/red mean an actual state change.
const SIZE = 196
const STROKE = 10
const RADIUS = (SIZE - STROKE) / 2
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

function statusColor(percent, thresholds) {
  if (percent >= thresholds.critical) return '#ff5d5d'
  if (percent >= thresholds.elevated) return '#ffb454'
  return '#4ee6b8'
}

export default function GaugeRing({
  value = 0,
  label,
  sublabel,
  unit = '%',
  thresholds = { elevated: 75, critical: 92 },
}) {
  const clamped = Math.max(0, Math.min(100, value))
  const color = statusColor(clamped, thresholds)
  const offset = CIRCUMFERENCE * (1 - clamped / 100)

  return (
    <div className="flex flex-col items-center justify-center">
      <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`}>
        <circle
          cx={SIZE / 2}
          cy={SIZE / 2}
          r={RADIUS}
          fill="none"
          stroke="#211f2c"
          strokeWidth={STROKE}
        />
        <circle
          cx={SIZE / 2}
          cy={SIZE / 2}
          r={RADIUS}
          fill="none"
          stroke={color}
          strokeWidth={STROKE}
          strokeLinecap="round"
          strokeDasharray={CIRCUMFERENCE}
          strokeDashoffset={offset}
          transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}
          style={{ transition: 'stroke-dashoffset 0.6s ease, stroke 0.4s ease' }}
        />
        <text
          x="50%"
          y="48%"
          textAnchor="middle"
          className="fill-ink font-mono"
          style={{ fontSize: 34, fontWeight: 600 }}
        >
          {Math.round(clamped)}
          <tspan style={{ fontSize: 16, fill: '#6f6b80' }}>{unit}</tspan>
        </text>
        <text
          x="50%"
          y="64%"
          textAnchor="middle"
          className="fill-ink-muted font-mono"
          style={{ fontSize: 11 }}
        >
          {sublabel}
        </text>
      </svg>
      <div className="mt-1 text-sm text-ink-muted">{label}</div>
    </div>
  )
}

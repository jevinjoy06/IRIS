import Sparkline from './Sparkline'

export default function StatTile({ label, value, unit = '%', detail, history = [], color = '#4ee6b8' }) {
  return (
    <div className="rounded-lg border border-hairline bg-panel p-4 flex flex-col gap-2">
      <div className="flex items-baseline justify-between">
        <span className="text-sm text-ink-muted">{label}</span>
        <span className="font-mono text-2xl text-ink">
          {value}
          <span className="text-sm text-ink-muted">{unit}</span>
        </span>
      </div>
      <Sparkline data={history} color={color} />
      {detail && <div className="text-xs font-mono text-ink-muted">{detail}</div>}
    </div>
  )
}

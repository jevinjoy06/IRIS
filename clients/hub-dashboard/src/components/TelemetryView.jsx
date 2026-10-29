import GaugeRing from './GaugeRing'
import StatTile from './StatTile'
import Sparkline from './Sparkline'

export default function TelemetryView({ system, status, history }) {
  if (!system) {
    return (
      <div className="flex-1 flex items-center justify-center text-ink-muted font-mono text-sm">
        waiting for first reading…
      </div>
    )
  }

  const gpu = system.gpu
  const hostLine = `${system.hostname} · ${system.os} ${system.os_version}`

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="text-sm text-ink-muted font-mono mb-6">{hostLine}</div>

      <div className="grid grid-cols-[auto_1fr] gap-6">
        <div className="rounded-lg border border-hairline bg-panel p-6 flex flex-col items-center gap-3">
          {gpu ? (
            <>
              <GaugeRing
                value={gpu.utilization_percent}
                label="GPU"
                sublabel={`${Math.round(gpu.vram_used_mb)}/${Math.round(gpu.vram_total_mb)} MB`}
              />
              <div className="text-xs text-ink-muted text-center max-w-[180px]">
                {gpu.name}
                <br />
                {gpu.temperature_c}°C
              </div>
              <Sparkline data={history.gpu} />
            </>
          ) : (
            <div className="text-sm text-ink-muted h-[196px] flex items-center">no NVIDIA GPU detected</div>
          )}
        </div>

        <div className="grid grid-cols-2 gap-4">
          <StatTile
            label="CPU"
            value={system.cpu_percent.toFixed(1)}
            history={history.cpu}
            color="#4ee6b8"
          />
          <StatTile
            label="RAM"
            value={system.ram_percent.toFixed(1)}
            detail={`${system.ram_used_gb} / ${system.ram_total_gb} GB`}
            history={history.ram}
            color="#4ee6b8"
          />
          <StatTile
            label="Disk"
            value={system.disk_percent.toFixed(1)}
            history={history.disk}
            color="#4ee6b8"
          />
          <div className="rounded-lg border border-hairline bg-panel p-4 flex flex-col gap-2">
            <span className="text-sm text-ink-muted">Model</span>
            <span className="font-mono text-lg text-violet truncate">{status?.model ?? '—'}</span>
            <span className="text-xs font-mono text-ink-muted">
              {status?.connected_clients ?? 0} client{status?.connected_clients === 1 ? '' : 's'} connected
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}

import { useEffect, useState, useCallback } from 'react'

const TIER_COLOR = { core: '#7c6aff', relevant: '#4ee6b8', archive: '#6f6b80' }

export default function MemoryView({ hubHttp }) {
  const [facts, setFacts] = useState(null)
  const [error, setError] = useState(null)
  const [filter, setFilter] = useState('all')

  const load = useCallback(() => {
    fetch(`${hubHttp}/api/facts`)
      .then(r => r.json())
      .then(setFacts)
      .catch(e => setError(String(e)))
  }, [hubHttp])

  useEffect(() => { load() }, [load])

  const remove = async (id) => {
    await fetch(`${hubHttp}/api/facts/${id}`, { method: 'DELETE' })
    load()
  }

  if (error) {
    return <div className="flex-1 p-6 text-critical font-mono text-sm">couldn't reach the hub: {error}</div>
  }
  if (!facts) {
    return <div className="flex-1 flex items-center justify-center text-ink-muted font-mono text-sm">loading facts…</div>
  }

  const tiers = ['core', 'relevant', 'archive']
  const visible = filter === 'all' ? facts : facts.filter(f => f.tier === filter)
  const counts = Object.fromEntries(tiers.map(t => [t, facts.filter(f => f.tier === t).length]))

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="flex items-center gap-2 mb-5">
        <button
          onClick={() => setFilter('all')}
          className="text-sm px-3 py-1.5 rounded-md border border-hairline"
          style={{ background: filter === 'all' ? 'rgba(124,106,255,0.12)' : 'transparent', color: filter === 'all' ? '#7c6aff' : '#6f6b80' }}
        >
          All ({facts.length})
        </button>
        {tiers.map(t => (
          <button
            key={t}
            onClick={() => setFilter(t)}
            className="text-sm px-3 py-1.5 rounded-md border border-hairline capitalize"
            style={{ background: filter === t ? 'rgba(124,106,255,0.12)' : 'transparent', color: filter === t ? TIER_COLOR[t] : '#6f6b80' }}
          >
            {t} ({counts[t]})
          </button>
        ))}
      </div>

      {visible.length === 0 ? (
        <div className="text-ink-muted font-mono text-sm">no facts in this tier yet</div>
      ) : (
        <div className="flex flex-col gap-2">
          {visible.map(f => (
            <div key={f.id} className="rounded-lg border border-hairline bg-panel p-3 flex items-start justify-between gap-4">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-mono capitalize" style={{ color: TIER_COLOR[f.tier] }}>{f.tier}</span>
                  <span className="text-xs font-mono text-ink-muted">importance {f.importance}</span>
                </div>
                <div className="text-sm text-ink">{f.content}</div>
              </div>
              <button
                onClick={() => remove(f.id)}
                className="text-xs font-mono text-ink-muted hover:text-critical shrink-0"
              >
                delete
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

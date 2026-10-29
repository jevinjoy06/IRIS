export default function SettingsView({ status }) {
  return (
    <div className="flex-1 p-6">
      <div className="rounded-lg border border-hairline bg-panel p-5 max-w-md">
        <div className="text-sm text-ink-muted mb-4">Current configuration (read-only)</div>
        <dl className="flex flex-col gap-3 font-mono text-sm">
          <div className="flex justify-between gap-4">
            <dt className="text-ink-muted">Model</dt>
            <dd className="text-ink truncate">{status?.model ?? '—'}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-ink-muted">Ollama URL</dt>
            <dd className="text-ink truncate">{status?.ollama_url ?? '—'}</dd>
          </div>
        </dl>
      </div>
      <p className="text-sm text-ink-muted mt-4 max-w-md leading-relaxed">
        Editing model, temperature, and the Tavily key from here needs a
        settings endpoint on the hub that doesn't exist yet — reading .env
        directly from the UI isn't the right shape for secrets. Next step.
      </p>
    </div>
  )
}

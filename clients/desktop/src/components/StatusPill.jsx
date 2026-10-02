export default function StatusPill({ connected, onReconnect }) {
  return (
    <div className="absolute top-4 right-4 z-20">
      <button
        onClick={!connected ? onReconnect : undefined}
        disabled={connected}
        title={connected ? 'Connected' : 'Hub disconnected — click to retry'}
        className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/[0.05] backdrop-blur-xl border border-white/[0.07] disabled:cursor-default hover:border-white/[0.14] transition-colors duration-300"
      >
        <div className={`w-1.5 h-1.5 rounded-full transition-colors duration-500 ${
          connected ? 'bg-emerald-400' : 'bg-orange-400 animate-pulse'
        }`} />
        <span className="text-[10px] font-mono tracking-[0.22em] uppercase text-white/35 select-none">
          IRIS
        </span>
      </button>
    </div>
  )
}

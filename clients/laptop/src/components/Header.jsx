export default function Header({ connected, hubUrl, onReconnect }) {
  return (
    <div className="shrink-0">
      <div className="flex items-center justify-between px-4 py-3 bg-[#1a1a1a] border-b border-white/10">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-blue-500" />
          <span className="font-semibold text-sm tracking-widest uppercase text-white/80">IRIS</span>
        </div>
        <div className="flex items-center gap-2 text-xs text-white/40">
          {connected && <div className="w-1.5 h-1.5 rounded-full bg-green-400" />}
          <span className="font-mono truncate max-w-52">{hubUrl}</span>
        </div>
      </div>

      {!connected && (
        <div className="flex items-center justify-between px-4 py-2 bg-orange-950/80 border-b border-orange-800/60">
          <div className="flex items-center gap-2">
            <div className="w-1.5 h-1.5 rounded-full bg-orange-400 animate-pulse" />
            <span className="text-orange-300 text-xs">Disconnected — waiting for hub</span>
          </div>
          <button
            onClick={onReconnect}
            className="text-xs bg-orange-800 hover:bg-orange-700 px-3 py-1 rounded-lg transition-colors text-orange-200"
          >
            Retry now
          </button>
        </div>
      )}
    </div>
  )
}

export default function Header({ connected, hubUrl }) {
  return (
    <div className="flex items-center justify-between px-4 py-3 bg-[#1a1a1a] border-b border-white/10 shrink-0">
      <div className="flex items-center gap-2">
        <div className="w-2 h-2 rounded-full bg-blue-500" />
        <span className="font-semibold text-sm tracking-widest uppercase text-white/80">IRIS</span>
      </div>
      <div className="flex items-center gap-2 text-xs text-white/40">
        <div className={`w-1.5 h-1.5 rounded-full ${connected ? 'bg-green-400' : 'bg-red-400'}`} />
        <span>{connected ? 'Connected' : 'Reconnecting...'}</span>
        <span className="hidden sm:inline text-white/20">·</span>
        <span className="hidden sm:inline font-mono truncate max-w-48">{hubUrl}</span>
      </div>
    </div>
  )
}

import { useEffect, useState } from 'react'

function wsToHttp(wsUrl) {
  return wsUrl.replace(/^ws(s?):\/\//, 'http$1://').replace(/\/ws$/, '')
}

export default function Sidebar({ hubUrl, connected }) {
  const [status, setStatus] = useState(null)

  useEffect(() => {
    const base = wsToHttp(hubUrl)
    const poll = async () => {
      try {
        const res = await fetch(`${base}/status`)
        setStatus(res.ok ? await res.json() : null)
      } catch {
        setStatus(null)
      }
    }
    poll()
    const id = setInterval(poll, 5000)
    return () => clearInterval(id)
  }, [hubUrl])

  return (
    <aside className="w-52 bg-[#111111] border-r border-white/10 flex flex-col p-4 gap-6 shrink-0">
      <div>
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-blue-500" />
          <span className="font-bold text-sm tracking-widest uppercase">IRIS</span>
        </div>
        <p className="text-white/20 text-[10px] font-mono mt-1 truncate">{hubUrl}</p>
      </div>

      <div>
        <p className="text-white/30 text-[10px] uppercase tracking-widest mb-2">Hub</p>
        <div className="flex items-center gap-2 mb-3">
          <div className={`w-1.5 h-1.5 rounded-full ${connected ? 'bg-green-400' : 'bg-red-400'}`} />
          <span className="text-sm">{connected ? 'Online' : 'Offline'}</span>
        </div>
        {status && (
          <div>
            <p className="text-white/30 text-[10px] uppercase tracking-widest mb-1">Model</p>
            <p className="text-xs font-mono text-white/60 truncate">{status.model}</p>
          </div>
        )}
      </div>

      {status && (
        <div>
          <p className="text-white/30 text-[10px] uppercase tracking-widest mb-2">Clients</p>
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-bold">{status.connected_clients}</span>
            <span className="text-xs text-white/30">connected</span>
          </div>
        </div>
      )}
    </aside>
  )
}

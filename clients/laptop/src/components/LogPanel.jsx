import { useEffect, useRef } from 'react'

function fmt(ts) {
  if (!ts) return '--:--:--'
  const d = new Date(ts)
  return [d.getHours(), d.getMinutes(), d.getSeconds()]
    .map(n => String(n).padStart(2, '0'))
    .join(':')
}

const ROLE_LABEL = { user: 'you', assistant: 'iris', tool: 'tool' }
const ROLE_COLOR = {
  user:      'text-white/35',
  assistant: 'text-cyan-400/60',
  tool:      'text-violet-400/50',
}

export default function LogPanel({ open, onClose, messages }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  useEffect(() => {
    if (open) bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [open, messages])

  return (
    <div className={`absolute inset-0 z-20 ${open ? 'pointer-events-auto' : 'pointer-events-none'}`}>
      <div
        className={`absolute inset-0 bg-black/50 backdrop-blur-sm transition-opacity duration-300 ${open ? 'opacity-100' : 'opacity-0'}`}
        onClick={onClose}
      />
      <div
        className="absolute bottom-0 left-0 right-0 h-[60%] bg-[#07071a]/95 border-t border-white/[0.07] rounded-t-2xl flex flex-col transition-transform duration-300 overflow-hidden"
        style={{ transform: open ? 'translateY(0)' : 'translateY(100%)' }}
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-white/[0.05] shrink-0">
          <span className="text-[10px] font-mono tracking-[0.25em] uppercase text-white/20">
            Session log
          </span>
          <button
            onClick={onClose}
            className="text-white/20 hover:text-white/55 transition-colors leading-none text-sm"
          >
            ✕
          </button>
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto px-5 py-3 space-y-1">
          {messages.length === 0 && (
            <p className="text-[11px] font-mono text-white/15 mt-4 text-center tracking-widest">
              no messages yet
            </p>
          )}
          {messages.map(msg => (
            <div key={msg.id} className="flex items-start gap-3 min-w-0">
              <span className="text-[10px] font-mono text-white/15 shrink-0 pt-px w-[58px]">
                {fmt(msg.ts)}
              </span>
              <span className={`text-[10px] font-mono shrink-0 pt-px w-[28px] ${ROLE_COLOR[msg.role] ?? 'text-white/25'}`}>
                {ROLE_LABEL[msg.role] ?? msg.role}
              </span>
              <p className="text-[12px] font-mono text-white/55 leading-relaxed break-words min-w-0 flex-1">
                {msg.text || (msg.streaming ? '…' : '')}
                {msg.streaming && (
                  <span className="ml-0.5 text-white/20 animate-pulse">|</span>
                )}
                {msg.error && (
                  <span className="ml-1 text-red-400/60">[error]</span>
                )}
              </p>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
      </div>
    </div>
  )
}

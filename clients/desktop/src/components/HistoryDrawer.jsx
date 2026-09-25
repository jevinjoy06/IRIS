import { useEffect } from 'react'
import ChatWindow from './ChatWindow'

export default function HistoryDrawer({ open, onClose, messages }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className={`absolute inset-0 z-20 ${open ? 'pointer-events-auto' : 'pointer-events-none'}`}>
      <div
        className={`absolute inset-0 bg-black/50 backdrop-blur-sm transition-opacity duration-300 ${open ? 'opacity-100' : 'opacity-0'}`}
        onClick={onClose}
      />
      <div
        className="absolute bottom-0 left-0 right-0 h-[60%] bg-[#08081a] border-t border-white/[0.07] rounded-t-2xl flex flex-col transition-transform duration-300 overflow-hidden"
        style={{ transform: open ? 'translateY(0)' : 'translateY(100%)' }}
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-white/[0.06] shrink-0">
          <span className="text-[10px] font-mono tracking-[0.25em] uppercase text-white/25">
            Conversation history
          </span>
          <button
            onClick={onClose}
            className="text-white/25 hover:text-white/60 transition-colors leading-none text-base"
          >
            ✕
          </button>
        </div>
        <div className="flex-1 min-h-0">
          <ChatWindow messages={messages} />
        </div>
      </div>
    </div>
  )
}

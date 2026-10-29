import { useRef, useState, useEffect } from 'react'

export default function ChatDrawer({ open, onClose, connected, sending, messages, send }) {
  const [input, setInput] = useState('')
  const listRef = useRef(null)

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight })
  }, [messages])

  const submit = () => {
    if (!input.trim() || sending) return
    send(input)
    setInput('')
  }

  return (
    <div
      className="absolute top-0 right-0 h-full w-[340px] border-l border-hairline bg-panel flex flex-col transition-transform"
      style={{ transform: open ? 'translateX(0)' : 'translateX(100%)', zIndex: 20 }}
    >
      <div className="flex items-center justify-between px-4 py-3 border-b border-hairline">
        <div className="flex items-center gap-2">
          <span
            className="w-1.5 h-1.5 rounded-full"
            style={{ background: connected ? '#4ee6b8' : '#6f6b80' }}
          />
          <span className="text-sm text-violet font-medium">Ask IRIS</span>
        </div>
        <button onClick={onClose} className="text-ink-muted hover:text-ink text-sm">close</button>
      </div>

      <div ref={listRef} className="flex-1 overflow-y-auto p-3 flex flex-col gap-2">
        {messages.map(m => (
          <div key={m.id} className={m.role === 'user' ? 'self-end max-w-[85%]' : 'self-start max-w-[85%]'}>
            {m.role === 'tool' ? (
              <div className="text-xs font-mono text-ink-muted border border-hairline rounded px-2 py-1 inline-block">
                ⚙ {m.text}
              </div>
            ) : (
              <div
                className="text-sm rounded-lg px-3 py-2"
                style={{
                  background: m.role === 'user' ? 'rgba(124,106,255,0.12)' : '#0d0c14',
                  color: m.error ? '#ff5d5d' : '#e7e4ef',
                  border: '1px solid #211f2c',
                  whiteSpace: 'pre-wrap',
                }}
              >
                {m.text}
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="p-3 border-t border-hairline flex gap-2">
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') submit() }}
          placeholder={connected ? 'Message IRIS…' : 'connecting…'}
          disabled={!connected || sending}
          className="flex-1 bg-void border border-hairline rounded-md px-3 py-2 text-sm text-ink outline-none focus:border-violet"
        />
        <button
          onClick={submit}
          disabled={!connected || sending || !input.trim()}
          className="px-3 py-2 rounded-md text-sm font-medium disabled:opacity-40"
          style={{ background: '#7c6aff', color: '#07070d' }}
        >
          Send
        </button>
      </div>
    </div>
  )
}

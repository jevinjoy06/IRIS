import { useEffect, useRef } from 'react'
import Message from './Message'

export default function ChatWindow({ messages }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
      {messages.length === 0 && (
        <div className="flex flex-col items-center justify-center h-full gap-1 select-none">
          <span className="text-white/15 text-[11px] font-mono tracking-[0.25em] uppercase">Awaiting input</span>
        </div>
      )}
      {messages.map(msg => (
        <Message key={msg.id} message={msg} />
      ))}
      <div ref={bottomRef} />
    </div>
  )
}

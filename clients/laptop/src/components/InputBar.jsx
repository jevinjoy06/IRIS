import { useState, useRef } from 'react'

export default function InputBar({ onSend, disabled, onHistory }) {
  const [value, setValue] = useState('')
  const textareaRef = useRef(null)

  const handleSend = () => {
    const text = value.trim()
    if (!text || disabled) return
    onSend(text)
    setValue('')
    textareaRef.current?.focus()
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex items-end gap-2 bg-[#0c0c18]/85 backdrop-blur-md border border-white/[0.08] rounded-2xl px-3 py-2 focus-within:border-blue-500/30 transition-colors shadow-lg shadow-black/40">
      {onHistory && (
        <button
          onClick={onHistory}
          className="mb-0.5 p-1.5 rounded-lg text-white/25 hover:text-white/55 hover:bg-white/5 transition-colors shrink-0"
          title="Show history"
        >
          <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
            <path d="M4 6h16M4 12h16M4 18h10" strokeLinecap="round" />
          </svg>
        </button>
      )}
      <textarea
        ref={textareaRef}
        value={value}
        onChange={e => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        rows={1}
        placeholder={disabled ? 'Connecting...' : 'Ask IRIS — Enter to send'}
        className="flex-1 bg-transparent text-sm text-white placeholder-white/20 resize-none outline-none py-1 max-h-32 overflow-y-auto disabled:opacity-40"
      />
      <button
        onClick={handleSend}
        disabled={disabled || !value.trim()}
        className="mb-0.5 p-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-30 disabled:cursor-not-allowed transition-colors shrink-0"
      >
        <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
          <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
    </div>
  )
}

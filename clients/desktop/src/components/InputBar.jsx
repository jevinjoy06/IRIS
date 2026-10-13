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
    <div className="flex items-end gap-2 bg-white/[0.04] backdrop-blur-2xl border border-white/[0.07] rounded-2xl px-3 py-2.5 focus-within:border-white/[0.14] focus-within:shadow-[0_0_40px_rgba(99,102,241,0.07)] transition-all duration-300">
      <textarea
        ref={textareaRef}
        value={value}
        onChange={e => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        rows={1}
        placeholder={disabled ? 'Connecting...' : 'Say or type…'}
        className="flex-1 bg-transparent text-[13px] text-white/80 placeholder-white/20 resize-none outline-none py-1 max-h-28 overflow-y-auto disabled:opacity-30"
      />
      {onHistory && (
        <button
          onClick={onHistory}
          className="mb-0.5 p-1.5 rounded-lg text-white/15 hover:text-white/45 transition-colors duration-200 shrink-0"
          title="History"
        >
          <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
            <path d="M4 6h16M4 12h16M4 18h10" strokeLinecap="round" />
          </svg>
        </button>
      )}
      <button
        onClick={handleSend}
        disabled={disabled || !value.trim()}
        className="mb-0.5 p-1.5 rounded-lg text-white/25 hover:text-white/70 disabled:opacity-20 disabled:cursor-not-allowed transition-colors duration-200 shrink-0"
      >
        <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
          <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
    </div>
  )
}

import { useState, useRef, useEffect } from 'react'

export default function InputBar({ onSend, disabled, connected }) {
  const [expanded, setExpanded] = useState(false)
  const [value, setValue] = useState('')
  const textareaRef = useRef(null)

  useEffect(() => {
    if (expanded) textareaRef.current?.focus()
  }, [expanded])

  const collapse = () => {
    setExpanded(false)
    setValue('')
  }

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
    } else if (e.key === 'Escape') {
      collapse()
    }
  }

  if (!expanded) {
    return (
      <button
        onClick={() => setExpanded(true)}
        title="Type a message"
        className="flex items-center gap-2 bg-white/[0.04] backdrop-blur-xl border border-white/[0.07] rounded-full px-4 py-2 text-white/25 hover:text-white/55 hover:border-white/[0.14] transition-all duration-200 text-[12px]"
      >
        <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
          <path d="M4 5h16v10H9l-4 4V5Z" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        {!connected ? 'Connecting…' : 'Type a message'}
      </button>
    )
  }

  return (
    <div className="flex items-end gap-2 bg-white/[0.04] backdrop-blur-2xl border border-white/[0.07] rounded-2xl px-3 py-2.5 focus-within:border-white/[0.14] focus-within:shadow-[0_0_40px_rgba(99,102,241,0.07)] transition-all duration-300 w-[420px] max-w-[88vw]">
      <textarea
        ref={textareaRef}
        value={value}
        onChange={e => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        rows={1}
        placeholder={!connected ? 'Connecting...' : disabled ? 'Thinking…' : 'Say or type…'}
        className="flex-1 bg-transparent text-[13px] text-white/80 placeholder-white/20 resize-none outline-none py-1 max-h-28 overflow-y-auto disabled:opacity-30"
      />
      <button
        onClick={handleSend}
        disabled={disabled || !value.trim()}
        className="mb-0.5 p-2.5 -m-1 rounded-lg text-white/25 hover:text-white/70 disabled:opacity-20 disabled:cursor-not-allowed transition-colors duration-200 shrink-0"
        title="Send"
      >
        <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
          <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      <button
        onClick={collapse}
        className="mb-0.5 p-2.5 -m-1 rounded-lg text-white/15 hover:text-white/45 transition-colors duration-200 shrink-0"
        title="Close (Esc)"
      >
        <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
          <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
        </svg>
      </button>
    </div>
  )
}

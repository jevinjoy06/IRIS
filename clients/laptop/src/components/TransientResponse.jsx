import { useState, useEffect, useRef } from 'react'

// `streaming` drives the blinking cursor (text actually arriving right now).
// `active` is broader — also true while audio is synthesizing/playing — and
// is what suppresses the fade-out timer, so the response doesn't disappear
// mid-sentence just because the text itself finished arriving long before
// the spoken audio does.
export default function TransientResponse({ text, streaming, active }) {
  const [visible, setVisible] = useState(false)
  const timerRef = useRef(null)

  useEffect(() => {
    if (text || active) {
      clearTimeout(timerRef.current)
      setVisible(true)
    }
  }, [text, active])

  useEffect(() => {
    if (!active && text) {
      timerRef.current = setTimeout(() => setVisible(false), 8000)
    }
    return () => clearTimeout(timerRef.current)
  }, [active, text])

  return (
    <div
      className="absolute left-0 right-0 bottom-28 flex justify-center px-10 pointer-events-none z-10"
      style={{
        opacity: visible ? 1 : 0,
        transform: visible ? 'translateY(0)' : 'translateY(10px)',
        transition: 'opacity 0.7s ease, transform 0.7s ease',
      }}
    >
      <p className="text-2xl font-light tracking-wide leading-relaxed text-white/80 text-center max-w-2xl">
        {text}
        {streaming && (
          <span className="ml-1 text-white/30 animate-pulse">|</span>
        )}
      </p>
    </div>
  )
}

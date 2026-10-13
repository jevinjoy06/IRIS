import { useState, useEffect, useRef } from 'react'

export default function TransientResponse({ text, streaming }) {
  const [visible, setVisible] = useState(false)
  const timerRef = useRef(null)

  useEffect(() => {
    if (text || streaming) {
      clearTimeout(timerRef.current)
      setVisible(true)
    }
  }, [text, streaming])

  useEffect(() => {
    if (!streaming && text) {
      timerRef.current = setTimeout(() => setVisible(false), 8000)
    }
    return () => clearTimeout(timerRef.current)
  }, [streaming, text])

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

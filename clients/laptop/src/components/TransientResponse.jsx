import { useState, useEffect, useRef } from 'react'

export default function TransientResponse({ text, streaming }) {
  const [opacity, setOpacity] = useState(text || streaming ? 1 : 0)
  const timerRef = useRef(null)

  useEffect(() => {
    if (text || streaming) {
      clearTimeout(timerRef.current)
      setOpacity(1)
    }
  }, [text, streaming])

  useEffect(() => {
    if (!streaming && text) {
      timerRef.current = setTimeout(() => setOpacity(0), 5000)
    }
    return () => clearTimeout(timerRef.current)
  }, [streaming, text])

  return (
    <div
      className="absolute left-0 right-0 bottom-20 flex justify-center px-10 pointer-events-none z-10"
      style={{ opacity, transition: 'opacity 0.8s ease' }}
    >
      <p className="text-white/70 text-sm leading-relaxed font-light tracking-wide text-center max-w-lg">
        {text}
        {streaming && <span className="ml-0.5 animate-pulse text-white/40">▋</span>}
      </p>
    </div>
  )
}

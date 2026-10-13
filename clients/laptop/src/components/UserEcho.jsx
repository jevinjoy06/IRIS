import { useState, useEffect, useRef } from 'react'

export default function UserEcho({ text, streaming }) {
  const [visible, setVisible] = useState(false)
  const timerRef = useRef(null)

  useEffect(() => {
    if (text) {
      clearTimeout(timerRef.current)
      setVisible(true)
    }
  }, [text])

  useEffect(() => {
    if (streaming) {
      timerRef.current = setTimeout(() => setVisible(false), 1200)
    }
    return () => clearTimeout(timerRef.current)
  }, [streaming])

  return (
    <div
      className="absolute left-0 right-0 bottom-44 flex justify-center px-12 pointer-events-none z-10"
      style={{
        opacity: visible ? 1 : 0,
        transform: visible ? 'translateY(0)' : 'translateY(6px)',
        transition: 'opacity 0.6s ease, transform 0.6s ease',
      }}
    >
      <p className="text-[11px] font-mono tracking-[0.18em] text-white/28 text-center max-w-xl truncate">
        {text}
      </p>
    </div>
  )
}

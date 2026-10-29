import { useState, useEffect, useRef, useCallback } from 'react'
import StatusPill from './components/StatusPill'
import OrbHero from './components/OrbHero'
import InputBar from './components/InputBar'
import TransientResponse from './components/TransientResponse'

function useOrbSize() {
  const [size, setSize] = useState(() => Math.min(window.innerWidth, window.innerHeight) * 0.55)
  useEffect(() => {
    const onResize = () => setSize(Math.min(window.innerWidth, window.innerHeight) * 0.55)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])
  return size
}

export default function App() {
  const [messages, setMessages]       = useState([])
  const [connected, setConnected]     = useState(false)
  const [sending, setSending]         = useState(false)
  const [streaming, setStreaming]     = useState(false)
  const [working, setWorking]         = useState(false)
  const [speaking, setSpeaking]       = useState(false)
  const [awaitingAudio, setAwaitingAudio] = useState(false)
  const [revealResponse, setRevealResponse] = useState(false)
  const wsRef             = useRef(null)
  const streamingIdRef    = useRef(null)
  const reconnectTimerRef = useRef(null)
  const audioRef          = useRef(null)
  const audioTimeoutRef   = useRef(null)
  const orbSize = useOrbSize()

  const hubUrl = window.irisConfig?.hubUrl || 'ws://localhost:7865/ws'

  // The "talking" visual (growth pulse) is reserved strictly for when audio
  // is actually playing — text generates and synthesizes well before sound
  // exists, so if "streaming" fired on token arrival the orb would visibly
  // "talk" (and the text would appear) before anything is audible. Every
  // earlier phase (text generating, tool calls, waiting on synthesis) reads
  // as the same "working" visual instead — busy, not talking.
  const orbState = !connected
    ? 'disconnected'
    : speaking
      ? 'streaming'
      : (working || streaming || awaitingAudio)
        ? 'working'
        : sending
          ? 'thinking'
          : 'idle'

  // The response text should stay on screen for as long as she's actively
  // communicating it — waiting on synthesis or speaking — not just while
  // tokens are arriving, so it doesn't fade mid-sentence once revealed.
  const responseActive = awaitingAudio || speaking

  const lastAssistant = messages.filter(m => m.role === 'assistant').at(-1)

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.CONNECTING) return

    const ws = new WebSocket(hubUrl)
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      clearTimeout(reconnectTimerRef.current)
    }

    ws.onclose = () => {
      setConnected(false)
      setStreaming(false)
      setWorking(false)
      setSpeaking(false)
      setAwaitingAudio(false)
      clearTimeout(audioTimeoutRef.current)
      audioRef.current?.pause()
      if (streamingIdRef.current) {
        setMessages(prev =>
          prev.map(m =>
            m.id === streamingIdRef.current
              ? { ...m, text: m.text || 'Connection lost', streaming: false, error: true }
              : m
          )
        )
        streamingIdRef.current = null
        setSending(false)
        setRevealResponse(true)
      }
      reconnectTimerRef.current = setTimeout(connect, 3000)
    }

    ws.onerror = () => ws.close()

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data)
      if (msg.type === 'token') {
        setStreaming(true)
        setWorking(false)
        setMessages(prev => {
          const targetId = streamingIdRef.current ?? prev.findLast?.(m => m.role === 'assistant' && m.streaming)?.id
          return prev.map(m => m.id === targetId ? { ...m, text: m.text + msg.text } : m)
        })
      } else if (msg.type === 'tool_use') {
        setWorking(true)
        setMessages(prev => [
          ...prev,
          { id: crypto.randomUUID(), role: 'tool', text: msg.tool, streaming: false },
        ])
      } else if (msg.type === 'done') {
        setStreaming(false)
        setWorking(false)
        setMessages(prev =>
          prev.map(m => m.streaming ? { ...m, streaming: false } : m)
        )
        streamingIdRef.current = null
        setSending(false)

        // Bridge the gap between text finishing and audio arriving — TTS
        // synthesis takes a moment, and without this the orb would relax to
        // idle for that gap then jolt back to "talking" once audio starts.
        // If no audio shows up within the timeout (TTS disabled/unavailable
        // on the hub, or synthesis failed), give up gracefully rather than
        // leaving the orb looking permanently busy.
        setAwaitingAudio(true)
        clearTimeout(audioTimeoutRef.current)
        audioTimeoutRef.current = setTimeout(() => {
          // No audio showed up in time (TTS disabled/unavailable on the hub,
          // or synthesis failed) — fall back to revealing the text on its
          // own rather than leaving the response invisible forever.
          setAwaitingAudio(false)
          setRevealResponse(true)
        }, 4000)
      } else if (msg.type === 'error') {
        setStreaming(false)
        setWorking(false)
        setAwaitingAudio(false)
        setRevealResponse(true)
        clearTimeout(audioTimeoutRef.current)
        setMessages(prev =>
          prev.map(m =>
            m.streaming
              ? { ...m, text: msg.text || m.text, streaming: false, error: true }
              : m
          )
        )
        streamingIdRef.current = null
        setSending(false)
      } else if (msg.type === 'audio') {
        setAwaitingAudio(false)
        clearTimeout(audioTimeoutRef.current)
        try {
          const binary = atob(msg.data)
          const bytes = new Uint8Array(binary.length)
          for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
          const blob = new Blob([bytes], { type: `audio/${msg.format || 'wav'}` })
          const url = URL.createObjectURL(blob)

          audioRef.current?.pause()
          const audio = new Audio(url)
          audioRef.current = audio
          audio.onplay = () => { setSpeaking(true); setRevealResponse(true) }
          audio.onended = () => { setSpeaking(false); URL.revokeObjectURL(url) }
          audio.onerror = () => { setSpeaking(false); URL.revokeObjectURL(url) }
          audio.play().catch(() => setSpeaking(false))
        } catch {
          setSpeaking(false)
        }
      }
    }
  }, [hubUrl])

  const reconnect = useCallback(() => {
    clearTimeout(reconnectTimerRef.current)
    if (wsRef.current) {
      wsRef.current.onclose = null
      wsRef.current.close()
    }
    connect()
  }, [connect])

  useEffect(() => {
    connect()
    return () => {
      clearTimeout(reconnectTimerRef.current)
      clearTimeout(audioTimeoutRef.current)
      wsRef.current?.close()
      audioRef.current?.pause()
    }
  }, [connect])

  const sendMessage = useCallback((text) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    const userMsg      = { id: crypto.randomUUID(), role: 'user', text, streaming: false }
    const assistantMsg = { id: crypto.randomUUID(), role: 'assistant', text: '', streaming: true }
    streamingIdRef.current = assistantMsg.id
    setSending(true)
    setRevealResponse(false)
    setMessages(prev => [...prev, userMsg, assistantMsg])
    wsRef.current.send(JSON.stringify({ type: 'message', text }))
  }, [])

  return (
    <div className="relative h-screen bg-[#06060f] text-white overflow-hidden flex items-center justify-center">
      <OrbHero orbState={orbState} size={orbSize} />

      <StatusPill connected={connected} onReconnect={reconnect} />

      <TransientResponse
        key={lastAssistant?.id}
        text={revealResponse ? (lastAssistant?.text ?? '') : ''}
        streaming={speaking}
        active={responseActive}
      />

      <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-10 flex justify-center">
        <InputBar
          onSend={sendMessage}
          disabled={!connected || sending}
          connected={connected}
        />
      </div>
    </div>
  )
}

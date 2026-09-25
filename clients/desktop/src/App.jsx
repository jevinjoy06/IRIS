import { useState, useEffect, useRef, useCallback } from 'react'
import Header from './components/Header'
import OrbScene from './components/OrbScene'
import InputBar from './components/InputBar'
import TransientResponse from './components/TransientResponse'
import HistoryDrawer from './components/HistoryDrawer'

export default function App() {
  const [messages, setMessages]       = useState([])
  const [connected, setConnected]     = useState(false)
  const [sending, setSending]         = useState(false)
  const [streaming, setStreaming]     = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const wsRef             = useRef(null)
  const streamingIdRef    = useRef(null)
  const reconnectTimerRef = useRef(null)

  const hubUrl = window.irisConfig?.hubUrl || 'ws://localhost:7865/ws'

  const orbState = !connected
    ? 'disconnected'
    : streaming
      ? 'streaming'
      : sending
        ? 'thinking'
        : 'idle'

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
      }
      reconnectTimerRef.current = setTimeout(connect, 3000)
    }

    ws.onerror = () => ws.close()

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data)
      if (msg.type === 'token') {
        setStreaming(true)
        setMessages(prev =>
          prev.map(m => m.id === streamingIdRef.current ? { ...m, text: m.text + msg.text } : m)
        )
      } else if (msg.type === 'tool_use') {
        setMessages(prev => [
          ...prev,
          { id: crypto.randomUUID(), role: 'tool', text: msg.tool, streaming: false },
        ])
      } else if (msg.type === 'done') {
        setStreaming(false)
        setMessages(prev =>
          prev.map(m => m.id === streamingIdRef.current ? { ...m, streaming: false } : m)
        )
        streamingIdRef.current = null
        setSending(false)
      } else if (msg.type === 'error') {
        setStreaming(false)
        setMessages(prev =>
          prev.map(m =>
            m.id === streamingIdRef.current
              ? { ...m, text: msg.text, streaming: false, error: true }
              : m
          )
        )
        streamingIdRef.current = null
        setSending(false)
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
      wsRef.current?.close()
    }
  }, [connect])

  const sendMessage = useCallback((text) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    const userMsg      = { id: crypto.randomUUID(), role: 'user', text, streaming: false }
    const assistantMsg = { id: crypto.randomUUID(), role: 'assistant', text: '', streaming: true }
    streamingIdRef.current = assistantMsg.id
    setSending(true)
    setMessages(prev => [...prev, userMsg, assistantMsg])
    wsRef.current.send(JSON.stringify({ type: 'message', text }))
  }, [])

  return (
    <div className="relative h-screen bg-[#06060f] text-white overflow-hidden">
      <OrbScene orbState={orbState} />

      <div className="absolute top-0 left-0 right-0 z-10">
        <Header connected={connected} hubUrl={hubUrl} onReconnect={reconnect} />
      </div>

      <TransientResponse
        key={lastAssistant?.id}
        text={lastAssistant?.text ?? ''}
        streaming={streaming}
      />

      <div className="absolute bottom-4 left-4 right-4 z-10">
        <InputBar
          onSend={sendMessage}
          disabled={!connected || sending}
          onHistory={() => setHistoryOpen(true)}
        />
      </div>

      <HistoryDrawer
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        messages={messages}
      />
    </div>
  )
}

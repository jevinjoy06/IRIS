import { useState, useEffect, useRef, useCallback } from 'react'
import StatusPill from './components/StatusPill'
import OrbScene from './components/OrbScene'
import InputBar from './components/InputBar'
import TransientResponse from './components/TransientResponse'
import UserEcho from './components/UserEcho'
import LogPanel from './components/LogPanel'

export default function App() {
  const [messages, setMessages]       = useState([])
  const [connected, setConnected]     = useState(false)
  const [sending, setSending]         = useState(false)
  const [streaming, setStreaming]     = useState(false)
  const [logOpen, setLogOpen] = useState(false)
  const wsRef             = useRef(null)
  const streamingIdRef    = useRef(null)
  const reconnectTimerRef = useRef(null)

  // Configure hub_url for remote connection. Update to your desktop LAN IP or tunnel URL.
  const hubUrl = window.irisConfig?.hubUrl || 'ws://192.168.1.x:7865/ws'

  const orbState = !connected
    ? 'disconnected'
    : streaming
      ? 'streaming'
      : sending
        ? 'thinking'
        : 'idle'

  const lastAssistant = messages.filter(m => m.role === 'assistant').at(-1)
  const lastUser      = messages.filter(m => m.role === 'user').at(-1)

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
          { id: crypto.randomUUID(), role: 'tool', text: msg.tool, streaming: false, ts: Date.now() },
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
    const userMsg      = { id: crypto.randomUUID(), role: 'user',      text, streaming: false, ts: Date.now() }
    const assistantMsg = { id: crypto.randomUUID(), role: 'assistant', text: '', streaming: true, ts: Date.now() }
    streamingIdRef.current = assistantMsg.id
    setSending(true)
    setMessages(prev => [...prev, userMsg, assistantMsg])
    wsRef.current.send(JSON.stringify({ type: 'message', text }))
  }, [])

  return (
    <div className="relative h-screen bg-[#06060f] text-white overflow-hidden">
      <OrbScene orbState={orbState} />

      <StatusPill connected={connected} onReconnect={reconnect} />

      <UserEcho
        key={lastUser?.id}
        text={lastUser?.text ?? ''}
        streaming={streaming}
      />

      <TransientResponse
        key={lastAssistant?.id}
        text={lastAssistant?.text ?? ''}
        streaming={streaming}
      />

      <div className="absolute bottom-4 left-4 right-4 z-10">
        <InputBar
          onSend={sendMessage}
          disabled={!connected || sending}
          onHistory={() => setLogOpen(true)}
        />
      </div>

      <LogPanel
        open={logOpen}
        onClose={() => setLogOpen(false)}
        messages={messages}
      />
    </div>
  )
}

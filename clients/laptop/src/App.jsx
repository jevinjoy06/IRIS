import { useState, useEffect, useRef, useCallback } from 'react'
import Header from './components/Header'
import ChatWindow from './components/ChatWindow'
import InputBar from './components/InputBar'

export default function App() {
  const [messages, setMessages] = useState([])
  const [connected, setConnected] = useState(false)
  const [sending, setSending] = useState(false)
  const wsRef = useRef(null)
  const streamingIdRef = useRef(null)
  const reconnectTimerRef = useRef(null)

  const hubUrl = window.irisConfig?.hubUrl || 'ws://localhost:7865/ws'

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
        setMessages(prev =>
          prev.map(m => m.id === streamingIdRef.current ? { ...m, text: m.text + msg.text } : m)
        )
      } else if (msg.type === 'tool_use') {
        setMessages(prev => [
          ...prev,
          { id: crypto.randomUUID(), role: 'tool', text: msg.tool, streaming: false },
        ])
      } else if (msg.type === 'done') {
        setMessages(prev =>
          prev.map(m => m.id === streamingIdRef.current ? { ...m, streaming: false } : m)
        )
        streamingIdRef.current = null
        setSending(false)
      } else if (msg.type === 'error') {
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
    const userMsg = { id: crypto.randomUUID(), role: 'user', text, streaming: false }
    const assistantMsg = { id: crypto.randomUUID(), role: 'assistant', text: '', streaming: true }
    streamingIdRef.current = assistantMsg.id
    setSending(true)
    setMessages(prev => [...prev, userMsg, assistantMsg])
    wsRef.current.send(JSON.stringify({ type: 'message', text }))
  }, [])

  return (
    <div className="flex flex-col h-screen bg-[#0f0f0f] text-white">
      <Header connected={connected} hubUrl={hubUrl} onReconnect={reconnect} />
      <ChatWindow messages={messages} />
      <InputBar onSend={sendMessage} disabled={!connected || sending} />
    </div>
  )
}

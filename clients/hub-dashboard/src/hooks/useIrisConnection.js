import { useState, useRef, useCallback, useEffect } from 'react'

// Shared connection: the orb's live state and the chat drawer's messages both
// come from one persistent WebSocket, so the orb reflects IRIS's real state
// (connected/thinking/streaming) whether or not the chat drawer is open.
export default function useIrisConnection(hubWs) {
  const [messages, setMessages] = useState([])
  const [connected, setConnected] = useState(false)
  const [sending, setSending] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [working, setWorking] = useState(false)
  const wsRef = useRef(null)
  const streamingIdRef = useRef(null)
  const reconnectTimerRef = useRef(null)

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.CONNECTING || wsRef.current?.readyState === WebSocket.OPEN) return
    const ws = new WebSocket(hubWs)
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      clearTimeout(reconnectTimerRef.current)
    }

    ws.onclose = () => {
      setConnected(false)
      setStreaming(false)
      setSending(false)
      setWorking(false)
      streamingIdRef.current = null
      reconnectTimerRef.current = setTimeout(connect, 3000)
    }

    ws.onerror = () => ws.close()

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data)
      if (msg.type === 'token') {
        setStreaming(true)
        setWorking(false)
        setMessages(prev => prev.map(m => m.id === streamingIdRef.current ? { ...m, text: m.text + msg.text } : m))
      } else if (msg.type === 'tool_use') {
        setWorking(true)
        setMessages(prev => [...prev, { id: crypto.randomUUID(), role: 'tool', text: msg.tool }])
      } else if (msg.type === 'done') {
        setStreaming(false)
        setSending(false)
        setWorking(false)
        streamingIdRef.current = null
      } else if (msg.type === 'error') {
        setStreaming(false)
        setSending(false)
        setWorking(false)
        setMessages(prev => prev.map(m => m.id === streamingIdRef.current ? { ...m, text: msg.text || m.text, error: true } : m))
        streamingIdRef.current = null
      }
    }
  }, [hubWs])

  useEffect(() => {
    connect()
    return () => {
      clearTimeout(reconnectTimerRef.current)
      wsRef.current?.close()
    }
  }, [connect])

  const send = useCallback((text) => {
    if (!text.trim() || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    const userMsg = { id: crypto.randomUUID(), role: 'user', text }
    const assistantMsg = { id: crypto.randomUUID(), role: 'assistant', text: '' }
    streamingIdRef.current = assistantMsg.id
    setSending(true)
    setMessages(prev => [...prev, userMsg, assistantMsg])
    wsRef.current.send(JSON.stringify({ type: 'message', text }))
  }, [])

  const orbState = !connected
    ? 'disconnected'
    : working
      ? 'working'
      : streaming
        ? 'streaming'
        : sending
          ? 'thinking'
          : 'idle'

  return { messages, connected, sending, streaming, working, orbState, send }
}

import { useState, useEffect, useRef } from 'react'
import NavRail from './components/NavRail'
import TelemetryView from './components/TelemetryView'
import MemoryView from './components/MemoryView'
import ActivityView from './components/ActivityView'
import SettingsView from './components/SettingsView'
import ChatDrawer from './components/ChatDrawer'
import OrbHero from './components/OrbHero'
import useIrisConnection from './hooks/useIrisConnection'

const HISTORY_LEN = 40

export default function App() {
  const hubHttp = window.irisConfig?.hubHttp || 'http://localhost:7865'
  const hubWs = window.irisConfig?.hubWs || 'ws://localhost:7865/ws'
  const pollMs = window.irisConfig?.pollIntervalMs || 2000

  const [view, setView] = useState('telemetry')
  const [chatOpen, setChatOpen] = useState(false)
  const iris = useIrisConnection(hubWs)
  const lastAssistant = [...iris.messages].reverse().find(m => m.role === 'assistant')?.text
  const [system, setSystem] = useState(null)
  const [status, setStatus] = useState(null)
  const [pollError, setPollError] = useState(null)
  const historyRef = useRef({ cpu: [], ram: [], disk: [], gpu: [] })
  const [, forceTick] = useState(0)

  useEffect(() => {
    let cancelled = false

    const poll = async () => {
      try {
        const [sysRes, statusRes] = await Promise.all([
          fetch(`${hubHttp}/api/system`),
          fetch(`${hubHttp}/status`),
        ])
        const sysData = await sysRes.json()
        const statusData = await statusRes.json()
        if (cancelled) return
        if (sysData.ok) {
          const h = historyRef.current
          h.cpu = [...h.cpu, sysData.cpu_percent].slice(-HISTORY_LEN)
          h.ram = [...h.ram, sysData.ram_percent].slice(-HISTORY_LEN)
          h.disk = [...h.disk, sysData.disk_percent].slice(-HISTORY_LEN)
          if (sysData.gpu) h.gpu = [...h.gpu, sysData.gpu.utilization_percent].slice(-HISTORY_LEN)
          setSystem(sysData)
          forceTick(t => t + 1)
        }
        setStatus(statusData)
        setPollError(null)
      } catch (e) {
        if (!cancelled) setPollError(String(e))
      }
    }

    poll()
    const id = setInterval(poll, pollMs)
    return () => { cancelled = true; clearInterval(id) }
  }, [hubHttp, pollMs])

  return (
    <div className="relative h-screen flex bg-void text-ink overflow-hidden">
      <NavRail view={view} onChangeView={setView} chatOpen={chatOpen} onToggleChat={() => setChatOpen(o => !o)} />

      <div className="flex-1 flex flex-col">
        <header className="flex items-center gap-6 px-8 py-6 border-b border-hairline">
          <OrbHero orbState={iris.orbState} size={168} />
          <div className="flex flex-col gap-1.5 min-w-0">
            <div className="font-display font-semibold text-2xl tracking-tight">IRIS Control</div>
            <div className="text-sm font-mono text-ink-muted">
              {{
                disconnected: 'reconnecting…',
                thinking: 'thinking…',
                working: 'working…',
                streaming: 'responding…',
                idle: 'listening',
              }[iris.orbState]}
            </div>
            {lastAssistant && (
              <div className="text-sm text-ink-muted mt-1 line-clamp-2 max-w-md">{lastAssistant}</div>
            )}
          </div>
          {pollError && <div className="text-xs font-mono text-critical ml-auto shrink-0">hub unreachable</div>}
        </header>

        {view === 'telemetry' && <TelemetryView system={system} status={status} history={historyRef.current} />}
        {view === 'memory' && <MemoryView hubHttp={hubHttp} />}
        {view === 'activity' && <ActivityView />}
        {view === 'settings' && <SettingsView status={status} />}
      </div>

      <ChatDrawer
        open={chatOpen}
        onClose={() => setChatOpen(false)}
        connected={iris.connected}
        sending={iris.sending}
        messages={iris.messages}
        send={iris.send}
      />
    </div>
  )
}

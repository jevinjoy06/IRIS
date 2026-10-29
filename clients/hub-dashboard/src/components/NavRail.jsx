const icons = {
  telemetry: (
    <path d="M3 13h3l2-7 4 12 3-9 2 4h4" fill="none" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
  ),
  memory: (
    <>
      <rect x="4" y="4" width="16" height="16" rx="2" fill="none" strokeWidth="1.6" />
      <path d="M8 4v16M16 4v16M4 8h16M4 16h16" strokeWidth="1.2" />
    </>
  ),
  activity: (
    <path d="M3 12h4l2 6 4-14 3 8h5" fill="none" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
  ),
  settings: (
    <>
      <circle cx="12" cy="12" r="3.2" fill="none" strokeWidth="1.6" />
      <path
        d="M12 3v2.4M12 18.6V21M4.9 6.3l1.7 1.7M17.4 16l1.7 1.7M3 12h2.4M18.6 12H21M4.9 17.7l1.7-1.7M17.4 8l1.7-1.7"
        strokeWidth="1.4"
        strokeLinecap="round"
      />
    </>
  ),
  chat: (
    <path
      d="M4 5h16v10H9l-4 4V5Z"
      fill="none"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  ),
}

function NavIcon({ name, active, onClick, accent = '#7c6aff', title }) {
  return (
    <button
      onClick={onClick}
      title={title}
      className="w-10 h-10 rounded-md flex items-center justify-center transition-colors"
      style={{
        background: active ? 'rgba(124,106,255,0.12)' : 'transparent',
        color: active ? accent : '#6f6b80',
      }}
    >
      <svg width="20" height="20" viewBox="0 0 24 24" stroke="currentColor">
        {icons[name]}
      </svg>
    </button>
  )
}

export default function NavRail({ view, onChangeView, onToggleChat, chatOpen }) {
  return (
    <div className="w-16 border-r border-hairline flex flex-col items-center py-4 justify-between">
      <div className="flex flex-col gap-2">
        <NavIcon name="telemetry" title="Telemetry" active={view === 'telemetry'} onClick={() => onChangeView('telemetry')} />
        <NavIcon name="memory" title="Memory" active={view === 'memory'} onClick={() => onChangeView('memory')} />
        <NavIcon name="activity" title="Activity" active={view === 'activity'} onClick={() => onChangeView('activity')} />
        <NavIcon name="settings" title="Settings" active={view === 'settings'} onClick={() => onChangeView('settings')} />
      </div>
      <NavIcon name="chat" title="Ask IRIS" active={chatOpen} onClick={onToggleChat} />
    </div>
  )
}

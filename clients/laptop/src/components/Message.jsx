export default function Message({ message }) {
  const { role, text, streaming, error } = message

  if (role === 'tool') {
    return (
      <div className="flex justify-center">
        <span className="text-xs text-white/30 bg-white/5 px-3 py-1 rounded-full font-mono">
          [{text}]
        </span>
      </div>
    )
  }

  const isUser = role === 'user'

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[75%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap ${
          isUser
            ? 'bg-blue-600 text-white rounded-br-sm'
            : error
            ? 'bg-red-950 text-red-300 rounded-bl-sm border border-red-800'
            : 'bg-[#1a1a1a] text-white/90 rounded-bl-sm'
        }`}
      >
        {!text && streaming ? (
          <span className="animate-pulse text-white/30">▋</span>
        ) : (
          <>
            {text}
            {streaming && <span className="ml-0.5 animate-pulse text-white/30">▋</span>}
          </>
        )}
      </div>
    </div>
  )
}

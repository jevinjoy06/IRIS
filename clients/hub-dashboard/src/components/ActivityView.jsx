export default function ActivityView() {
  return (
    <div className="flex-1 flex items-center justify-center p-6">
      <div className="max-w-sm text-center">
        <div className="text-ink font-medium mb-2">No live feed yet</div>
        <p className="text-sm text-ink-muted leading-relaxed">
          Tool calls and session events currently only stream to the client
          that triggered them. Showing them here needs the hub to broadcast
          activity to observers, not just the active session — that's the
          next piece to build.
        </p>
      </div>
    </div>
  )
}

function StatusDot({ status }) {
  const color = status === 'running' ? 'bg-emerald-400'
    : status === 'error' ? 'bg-red-400'
    : 'bg-slate-500'

  return <span className={`w-1.5 h-1.5 rounded-full ${color}`} />
}

export default function AgentStatus({ agentsStatus, wsConnected }) {
  const agents = Object.entries(agentsStatus || {})

  return (
    <footer className="px-6 py-3 border-t border-slate-800 flex items-center gap-6 text-xs text-slate-500 flex-wrap">
      <div className="flex items-center gap-1.5">
        <span className={`w-1.5 h-1.5 rounded-full ${wsConnected ? 'bg-emerald-400' : 'bg-red-400'}`} />
        <span>WS {wsConnected ? 'connecté' : 'déconnecté'}</span>
      </div>
      {agents.map(([name, info]) => {
        const state = info?.state || (info?.last_activity ? 'active' : 'idle')
        const last = info?.last_activity
        return (
          <div key={name} className="flex items-center gap-1.5">
            <StatusDot status={state === 'running' || state === 'active' ? 'running' : 'idle'} />
            <span>{name.replace('_', ' ')}</span>
            {last?.duration_ms && <span className="text-slate-600">({last.duration_ms}ms)</span>}
          </div>
        )
      })}
    </footer>
  )
}

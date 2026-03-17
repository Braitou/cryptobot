import { useState } from 'react'

export default function KillSwitch({ killSwitch }) {
  const [loading, setLoading] = useState(false)
  const isKilled = killSwitch?.daily_kill || killSwitch?.total_kill

  const handleKill = async () => {
    if (!confirm('Activer le kill switch ? Le trading sera arrêté immédiatement.')) return
    setLoading(true)
    await fetch('/api/kill-switch', { method: 'POST' })
    setLoading(false)
    window.location.reload()
  }

  const handleResume = async () => {
    setLoading(true)
    await fetch('/api/resume', { method: 'POST' })
    setLoading(false)
    window.location.reload()
  }

  if (isKilled) {
    return (
      <div className="flex items-center gap-3">
        <span className="text-xs text-red-400 font-medium">KILL SWITCH ACTIF</span>
        <button
          onClick={handleResume}
          disabled={loading}
          className="px-3 py-1.5 text-xs font-medium rounded bg-slate-700 hover:bg-slate-600 text-slate-200 transition-colors"
        >
          Reprendre
        </button>
      </div>
    )
  }

  return (
    <button
      onClick={handleKill}
      disabled={loading}
      className="px-3 py-1.5 text-xs font-medium rounded bg-red-600/80 hover:bg-red-600 text-white transition-colors"
    >
      Kill Switch
    </button>
  )
}

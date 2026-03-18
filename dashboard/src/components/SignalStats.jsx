import { useState, useEffect } from 'react'

function StatLine({ label, value, bold, color = 'text-slate-500' }) {
  return (
    <div className="flex justify-between items-center">
      <span className={`text-xs ${color}`}>{label}</span>
      <span className={`text-xs font-mono ${bold ? 'font-bold text-slate-200' : color}`}>{value}</span>
    </div>
  )
}

export default function SignalStats({ stats, lastSignalTime }) {
  const [elapsed, setElapsed] = useState(null)

  useEffect(() => {
    if (!lastSignalTime) return
    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - lastSignalTime) / 1000))
    }, 1000)
    return () => clearInterval(interval)
  }, [lastSignalTime])

  const s = stats || {}

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
      <h3 className="text-xs text-slate-400 mb-3">Signaux aujourd'hui</h3>
      <div className="space-y-1.5">
        <StatLine label="Analyses" value={s.analyzed || 0} bold />
        <StatLine label="Filtres ATR bas" value={s.filtered_atr_low || 0} />
        <StatLine label="Filtres micro-trend" value={s.filtered_micro_trend || 0} />
        <StatLine label="Filtres regime OFF" value={s.filtered_regime_off || 0} />
        <StatLine label="Bloques calendar" value={s.blocked_calendar || 0} />
        <StatLine label="Bloques correlation" value={s.blocked_correlation || 0} />
        <StatLine label="Bloques risk guard" value={s.blocked_risk_guard || 0} />
        <div className="border-t border-slate-800 pt-1.5 mt-1.5">
          <StatLine label="Executes" value={s.executed || 0} bold color="text-emerald-400" />
        </div>
      </div>
      {elapsed != null && (
        <div className="text-[10px] text-slate-600 mt-3">
          Dernier signal: il y a {elapsed}s
        </div>
      )}
    </div>
  )
}

const statusColors = {
  open: 'text-blue-400',
  closed_tp: 'text-emerald-400',
  closed_sl: 'text-red-400',
  closed_trailing: 'text-yellow-400',
  closed_timeout: 'text-slate-400',
  closed_manual: 'text-slate-400',
}

const statusLabels = {
  open: 'Ouvert',
  closed_tp: 'TP',
  closed_sl: 'SL',
  closed_trailing: 'Trail',
  closed_timeout: 'Timeout',
  closed_manual: 'Manuel',
}

function duration(entry, exit) {
  if (!entry || !exit) return '—'
  const ms = new Date(exit) - new Date(entry)
  const min = Math.floor(ms / 60000)
  if (min < 60) return `${min}m`
  return `${Math.floor(min / 60)}h${(min % 60).toString().padStart(2, '0')}m`
}

export default function TradeHistory({ trades }) {
  const recent = (trades || []).slice(0, 15)

  if (recent.length === 0) {
    return (
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
        <h3 className="text-sm font-medium text-slate-300 mb-2">Historique des trades</h3>
        <div className="text-xs text-slate-500">Aucun trade</div>
      </div>
    )
  }

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
      <div className="px-4 py-2 border-b border-slate-800">
        <h3 className="text-sm font-medium text-slate-300">Historique des trades</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-slate-500 border-b border-slate-800">
              <th className="px-3 py-2 text-left">#</th>
              <th className="px-3 py-2 text-left">Paire</th>
              <th className="px-3 py-2 text-left">Side</th>
              <th className="px-3 py-2 text-right font-mono">Entrée</th>
              <th className="px-3 py-2 text-right font-mono">Sortie</th>
              <th className="px-3 py-2 text-right font-mono">P&L</th>
              <th className="px-3 py-2 text-center">Durée</th>
              <th className="px-3 py-2 text-center">Sortie</th>
              <th className="px-3 py-2 text-left">Décision IA</th>
            </tr>
          </thead>
          <tbody>
            {recent.map(t => {
              const pnl = t.pnl_pct ?? 0
              return (
                <tr key={t.id} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                  <td className="px-3 py-2 text-slate-500">{t.id}</td>
                  <td className="px-3 py-2 font-medium">{t.pair}</td>
                  <td className={`px-3 py-2 font-medium ${t.side === 'BUY' ? 'text-emerald-400' : 'text-red-400'}`}>
                    {t.side}
                  </td>
                  <td className="px-3 py-2 text-right font-mono">{t.entry_price?.toFixed(2)}</td>
                  <td className="px-3 py-2 text-right font-mono">{t.exit_price?.toFixed(2) ?? '—'}</td>
                  <td className={`px-3 py-2 text-right font-mono font-medium ${pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {t.status === 'open' ? '—' : `${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}%`}
                  </td>
                  <td className="px-3 py-2 text-center text-slate-400">{duration(t.entry_time, t.exit_time)}</td>
                  <td className={`px-3 py-2 text-center font-medium ${statusColors[t.status] || 'text-slate-400'}`}>
                    {statusLabels[t.status] || t.status}
                  </td>
                  <td className="px-3 py-2 text-slate-400 max-w-[200px] truncate">
                    {t.decision_reasoning?.slice(0, 80) || '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

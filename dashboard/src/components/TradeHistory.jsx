const statusColors = {
  open: 'text-blue-400',
  closed_tp: 'text-emerald-400',
  closed_sl: 'text-red-400',
  closed_trailing: 'text-yellow-400',
  closed_timeout: 'text-slate-400',
  closed_scalp_exit: 'text-orange-400',
  closed_manual: 'text-slate-400',
}

const statusLabels = {
  open: 'Ouvert',
  closed_tp: 'TP',
  closed_sl: 'SL',
  closed_trailing: 'Trail',
  closed_timeout: 'Timeout',
  closed_scalp_exit: 'Exit',
  closed_manual: 'Manuel',
}

function duration(entry, exit) {
  if (!entry || !exit) return '--'
  const ms = new Date(exit) - new Date(entry)
  const min = Math.floor(ms / 60000)
  if (min < 60) return `${min}m`
  return `${Math.floor(min / 60)}h${(min % 60).toString().padStart(2, '0')}m`
}

function tradeMode(marketAnalysis) {
  if (!marketAnalysis) return '--'
  if (marketAnalysis.includes('SCALP')) return 'SCALP'
  if (marketAnalysis.includes('MOMENTUM')) return 'MOM'
  return marketAnalysis.slice(0, 8)
}

function tradeRegime(marketAnalysis) {
  if (!marketAnalysis) return ''
  const parts = marketAnalysis.split('_')
  // SCALP_AUTO_RANGING → RANGING
  if (parts.length >= 3) return parts.slice(2).join('_')
  return ''
}

export default function TradeHistory({ trades }) {
  const closed = (trades || []).filter(t => t.status !== 'open').slice(0, 20)

  if (closed.length === 0) {
    return (
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
        <h3 className="text-sm font-medium text-slate-300 mb-2">Trades recents</h3>
        <div className="text-xs text-slate-500">Aucun trade</div>
      </div>
    )
  }

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
      <div className="px-4 py-2 border-b border-slate-800">
        <h3 className="text-sm font-medium text-slate-300">Trades recents</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-slate-500 border-b border-slate-800">
              <th className="px-2 py-2 text-left">#</th>
              <th className="px-2 py-2 text-left">Paire</th>
              <th className="px-2 py-2 text-right font-mono">P&L net</th>
              <th className="px-2 py-2 text-center">Duree</th>
              <th className="px-2 py-2 text-center">Sortie</th>
              <th className="px-2 py-2 text-center">Mode</th>
              <th className="px-2 py-2 text-center">Regime</th>
            </tr>
          </thead>
          <tbody>
            {closed.map(t => {
              const pnl = t.pnl_pct ?? 0
              const mode = tradeMode(t.market_analysis)
              const regime = tradeRegime(t.market_analysis)

              return (
                <tr key={t.id} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                  <td className="px-2 py-1.5 text-slate-500">{t.id}</td>
                  <td className="px-2 py-1.5 font-medium">{t.pair?.replace('USDT', '')}</td>
                  <td className={`px-2 py-1.5 text-right font-mono font-bold ${pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {pnl >= 0 ? '+' : ''}{pnl.toFixed(2)}%
                  </td>
                  <td className="px-2 py-1.5 text-center text-slate-400">{duration(t.entry_time, t.exit_time)}</td>
                  <td className={`px-2 py-1.5 text-center font-medium ${statusColors[t.status] || 'text-slate-400'}`}>
                    {statusLabels[t.status] || t.status}
                  </td>
                  <td className="px-2 py-1.5 text-center">
                    <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                      mode === 'SCALP'
                        ? 'bg-blue-500/20 text-blue-400'
                        : 'bg-purple-500/20 text-purple-400'
                    }`}>{mode}</span>
                  </td>
                  <td className="px-2 py-1.5 text-center text-slate-500 text-[10px]">{regime || '--'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

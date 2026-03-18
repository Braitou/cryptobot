export default function OpenPositions({ positions }) {
  if (!positions || positions.length === 0) return null

  return (
    <div className="px-6">
      <h3 className="text-sm font-medium text-slate-300 mb-3">Positions ouvertes</h3>
      <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-3">
        {positions.map(pos => (
          <PositionCard key={pos.id} pos={pos} />
        ))}
      </div>
    </div>
  )
}

function PositionCard({ pos }) {
  const entry = pos.entry_price || 0
  const current = pos.current_price || entry
  const sl = pos.stop_loss || 0
  const tp = pos.take_profit || 0
  const pnl = pos.unrealized_pnl || 0
  const pnlPct = pos.unrealized_pct || 0
  const isPositive = pnl >= 0
  const mode = (pos.market_analysis || '').includes('SCALP') ? 'SCALP' : 'MOM'

  // Barre visuelle SL → Entry → TP
  const range = tp - sl
  const entryPos = range > 0 ? ((entry - sl) / range) * 100 : 50
  const currentPos = range > 0 ? ((current - sl) / range) * 100 : 50

  // Timeout restant
  let timeoutText = ''
  if (pos.entry_time) {
    const entryTime = new Date(pos.entry_time).getTime()
    const maxHold = (pos.max_hold_minutes || 30) * 60000
    const remaining = Math.max(0, (entryTime + maxHold - Date.now()) / 60000)
    timeoutText = remaining > 0 ? `${Math.floor(remaining)}min` : 'expire'
  }

  return (
    <div className="bg-slate-900 border border-blue-500/30 rounded-lg p-3">
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold text-slate-200">{pos.pair?.replace('USDT', '')}</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
            {pos.side}
          </span>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
            {mode}
          </span>
        </div>
        <span className={`text-lg font-mono font-bold ${isPositive ? 'text-emerald-400' : 'text-red-400'}`}>
          {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%
        </span>
      </div>

      {/* Grille de valeurs */}
      <div className="grid grid-cols-5 gap-1 text-[10px] text-center mb-2">
        <div><div className="text-slate-500">Entree</div><div className="font-mono text-slate-300">{entry.toFixed(2)}</div></div>
        <div><div className="text-slate-500">Actuel</div><div className={`font-mono ${isPositive ? 'text-emerald-400' : 'text-red-400'}`}>{current.toFixed(2)}</div></div>
        <div><div className="text-slate-500">SL</div><div className="font-mono text-red-400">{sl.toFixed(2)}</div></div>
        <div><div className="text-slate-500">TP</div><div className="font-mono text-emerald-400">{tp.toFixed(2)}</div></div>
        <div><div className="text-slate-500">Timeout</div><div className="font-mono text-slate-400">{timeoutText}</div></div>
      </div>

      {/* Barre visuelle */}
      <div className="relative h-2 bg-gradient-to-r from-red-500/30 via-slate-700 to-emerald-500/30 rounded-full">
        {/* Trait entrée */}
        <div className="absolute top-0 h-full w-0.5 bg-slate-300" style={{ left: `${Math.min(Math.max(entryPos, 2), 98)}%` }} />
        {/* Trait prix actuel */}
        <div className="absolute top-0 h-full w-1 bg-blue-400 rounded-full" style={{ left: `${Math.min(Math.max(currentPos, 1), 99)}%` }} />
      </div>
      <div className="flex justify-between text-[9px] text-slate-600 mt-0.5">
        <span>SL</span>
        <span>TP</span>
      </div>
    </div>
  )
}

import { useMemo } from 'react'

export default function PairWinRate({ trades }) {
  const pairStats = useMemo(() => {
    const closed = (trades || []).filter(t => t.status !== 'open' && t.pnl != null)
    const pairs = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']

    return pairs.map(pair => {
      const pairTrades = closed.filter(t => t.pair === pair)
      const wins = pairTrades.filter(t => t.pnl > 0).length
      const total = pairTrades.length
      const winRate = total > 0 ? (wins / total * 100) : 0

      return { pair, wins, total, winRate }
    })
  }, [trades])

  return (
    <div>
      <h4 className="text-xs text-slate-400 mb-2">Win rate par paire</h4>
      <div className="space-y-2">
        {pairStats.map(({ pair, wins, total, winRate }) => (
          <div key={pair} className="flex items-center gap-2">
            <span className="text-xs text-slate-500 w-8 shrink-0">{pair.replace('USDT', '')}</span>
            <div className="flex-1 h-3 bg-slate-800 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full ${winRate >= 50 ? 'bg-emerald-500' : winRate > 0 ? 'bg-orange-500' : 'bg-slate-700'}`}
                style={{ width: `${Math.max(winRate, 2)}%` }}
              />
            </div>
            <span className="text-xs text-slate-400 font-mono w-16 text-right">
              {total > 0 ? `${winRate.toFixed(0)}% (${wins}/${total})` : '--'}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

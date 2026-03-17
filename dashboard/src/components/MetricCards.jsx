function Card({ label, value, sub, color = 'slate' }) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
      <div className="text-xs text-slate-400 mb-1">{label}</div>
      <div className={`text-2xl font-mono font-bold ${
        color === 'green' ? 'text-emerald-400' :
        color === 'red' ? 'text-red-400' : 'text-slate-100'
      }`}>
        {value}
      </div>
      {sub && <div className="text-xs text-slate-500 mt-1">{sub}</div>}
    </div>
  )
}

function fmtPnl(v) {
  if (v == null) return '—'
  const sign = v >= 0 ? '+' : ''
  return `${sign}${v.toFixed(2)}`
}

export default function MetricCards({ portfolio, trades, config }) {
  if (!portfolio) return null

  const capital = portfolio.capital ?? 0
  const totalPnlPct = portfolio.total_pnl_pct ?? 0
  const dailyPnl = portfolio.daily_pnl ?? 0
  const drawdown = (portfolio.drawdown_pct ?? 0) * 100
  const openPos = portfolio.open_positions ?? 0

  const closedToday = trades.filter(t => t.status !== 'open')
  const winsToday = closedToday.filter(t => (t.pnl || 0) > 0).length

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 px-6">
      <Card
        label="Capital total"
        value={`${capital.toFixed(2)} USDT`}
        sub={`${fmtPnl(totalPnlPct)}% depuis le début`}
        color={totalPnlPct >= 0 ? 'green' : 'red'}
      />
      <Card
        label="P&L aujourd'hui"
        value={`${fmtPnl(dailyPnl)} USDT`}
        sub={`${closedToday.length} trades / ${winsToday} wins`}
        color={dailyPnl >= 0 ? 'green' : 'red'}
      />
      <Card
        label="Drawdown"
        value={`${drawdown.toFixed(1)}%`}
        sub="max 15%"
        color={drawdown > 10 ? 'red' : drawdown > 5 ? 'slate' : 'green'}
      />
      <Card
        label="Positions ouvertes"
        value={`${openPos} / ${config?.max_open_positions ?? 4}`}
        color="slate"
      />
    </div>
  )
}

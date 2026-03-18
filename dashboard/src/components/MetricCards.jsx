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
  if (v == null) return '--'
  const sign = v >= 0 ? '+' : ''
  return `${sign}${v.toFixed(2)}`
}

export default function MetricCards({ portfolio, trades, agentCosts }) {
  if (!portfolio) return null

  const capital = portfolio.capital ?? 0
  const totalPnlPct = portfolio.total_pnl_pct ?? 0
  const dailyPnl = portfolio.daily_pnl ?? 0

  // Trades fermés
  const closed = (trades || []).filter(t => t.status !== 'open')
  const closedToday = closed.filter(t => {
    if (!t.exit_time) return false
    const today = new Date().toISOString().slice(0, 10)
    return t.exit_time.slice(0, 10) === today
  })
  const todayCount = closedToday.length

  // Win rate global
  const wins = closed.filter(t => (t.pnl || 0) > 0).length
  const losses = closed.length - wins
  const winRate = closed.length > 0 ? (wins / closed.length * 100) : 0

  // Profit factor : somme gains / abs(somme pertes)
  const totalGains = closed.reduce((s, t) => s + Math.max(0, t.pnl || 0), 0)
  const totalLosses = closed.reduce((s, t) => s + Math.abs(Math.min(0, t.pnl || 0)), 0)
  const profitFactor = totalLosses > 0 ? totalGains / totalLosses : totalGains > 0 ? 99.9 : 0

  // Fréquence : trades des dernières 24h
  const now = Date.now()
  const last24h = closed.filter(t => {
    if (!t.exit_time) return false
    return (now - new Date(t.exit_time).getTime()) < 86400000
  }).length

  // Coût API mois
  const apiCostTotal = agentCosts?._total || portfolio?.api_cost_total || 0

  return (
    <div className="grid grid-cols-3 lg:grid-cols-6 gap-3 px-6">
      <Card
        label="Capital"
        value={`${capital.toFixed(2)}`}
        sub={`${fmtPnl(totalPnlPct)}% depuis le debut`}
        color={totalPnlPct >= 0 ? 'green' : 'red'}
      />
      <Card
        label="P&L net jour"
        value={`${fmtPnl(dailyPnl)} USDT`}
        sub={`${todayCount} trades aujourd'hui`}
        color={dailyPnl >= 0 ? 'green' : 'red'}
      />
      <Card
        label="Win rate"
        value={`${winRate.toFixed(0)}%`}
        sub={`${wins}W ${losses}L`}
        color={winRate >= 50 ? 'green' : winRate >= 40 ? 'slate' : 'red'}
      />
      <Card
        label="Profit factor"
        value={profitFactor >= 99 ? '--' : profitFactor.toFixed(2)}
        sub={profitFactor >= 1.1 ? 'rentable' : profitFactor > 0 ? 'en dessous' : 'aucun trade'}
        color={profitFactor >= 1.1 ? 'green' : profitFactor >= 0.9 ? 'slate' : 'red'}
      />
      <Card
        label="Frequence"
        value={`${last24h}/jour`}
        sub="cible 5-10"
        color={last24h >= 5 ? 'green' : last24h >= 1 ? 'slate' : 'red'}
      />
      <Card
        label="Cout API"
        value={`$${apiCostTotal.toFixed(2)}`}
        sub="/ $50 budget mois"
        color={apiCostTotal > 40 ? 'red' : 'slate'}
      />
    </div>
  )
}

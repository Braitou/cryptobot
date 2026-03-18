import { useMemo, useState } from 'react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Area, AreaChart } from 'recharts'

export default function EquityCurve({ trades, initialCapital = 500 }) {
  const [period, setPeriod] = useState('all')

  const data = useMemo(() => {
    if (!trades || trades.length === 0) return []

    // Trades fermés triés par date
    const closed = trades
      .filter(t => t.status !== 'open' && t.exit_time && t.pnl != null)
      .sort((a, b) => new Date(a.exit_time) - new Date(b.exit_time))

    if (closed.length === 0) return []

    // Filtrer par période
    const now = Date.now()
    const filtered = closed.filter(t => {
      if (period === '7d') return (now - new Date(t.exit_time).getTime()) < 7 * 86400000
      if (period === '30d') return (now - new Date(t.exit_time).getTime()) < 30 * 86400000
      return true
    })

    // Construire la courbe equity
    let equity = initialCapital
    const points = [{ time: 'Start', equity: initialCapital }]

    for (const t of filtered) {
      equity += (t.pnl || 0)
      points.push({
        time: new Date(t.exit_time).toLocaleDateString('fr', { day: '2-digit', month: '2-digit' }),
        equity: parseFloat(equity.toFixed(2)),
      })
    }

    return points
  }, [trades, initialCapital, period])

  if (!trades || trades.filter(t => t.status !== 'open').length < 2) {
    return (
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-6 flex items-center justify-center h-64">
        <span className="text-slate-500 text-sm">En attente de donnees...</span>
      </div>
    )
  }

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-slate-300">Equity Curve</h3>
        <div className="flex gap-1">
          {['7d', '30d', 'all'].map(p => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`text-xs px-2 py-0.5 rounded ${
                period === p
                  ? 'bg-slate-700 text-slate-200'
                  : 'text-slate-500 hover:text-slate-300'
              }`}
            >
              {p === 'all' ? 'All' : p.toUpperCase()}
            </button>
          ))}
        </div>
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <AreaChart data={data}>
          <defs>
            <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#10b981" stopOpacity={0.2} />
              <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#64748b' }} interval="preserveStartEnd" />
          <YAxis
            tick={{ fontSize: 10, fill: '#64748b' }}
            domain={['auto', 'auto']}
            tickFormatter={v => `${v}`}
          />
          <Tooltip
            contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 6, fontSize: 12 }}
            labelStyle={{ color: '#94a3b8' }}
            formatter={v => [`${v} USDT`, 'Equity']}
          />
          <Area type="monotone" dataKey="equity" stroke="#10b981" fill="url(#equityGrad)" strokeWidth={2} dot={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

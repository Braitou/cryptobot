import LearningCurve from './LearningCurve'

function AICard({ label, children }) {
  return (
    <div className="bg-slate-900 border border-blue-500/30 rounded-lg p-4">
      <div className="text-xs text-blue-400 mb-1.5 font-medium">{label}</div>
      {children}
    </div>
  )
}

export default function AIMetricCards({ trades, agentsCosts, memory }) {
  const closed = (trades || []).filter(t => t.status !== 'open')
  const totalCost = agentsCosts?._total ?? 0

  // Win rate par tranche de 20
  const tranches = []
  for (let i = 0; i < closed.length; i += 20) {
    const slice = closed.slice(i, i + 20)
    const wins = slice.filter(t => (t.pnl || 0) > 0).length
    tranches.push({ tranche: Math.floor(i / 20) + 1, winRate: Math.round((wins / slice.length) * 100) })
  }
  const currentWinRate = closed.length > 0
    ? Math.round(closed.filter(t => (t.pnl || 0) > 0).length / closed.length * 100)
    : 0

  // Accord inter-agents (approximation: trades avec décision BUY/SELL = agents d'accord)
  const recentDecisions = closed.slice(0, 50)
  const agreed = recentDecisions.filter(t => t.risk_evaluation && !t.risk_evaluation.includes('REJECT')).length
  const agreementPct = recentDecisions.length > 0
    ? Math.round(agreed / recentDecisions.length * 100)
    : 0

  // Qualité mémoire
  const entries = memory?.entries || []
  const avgConf = entries.length > 0
    ? entries.reduce((s, e) => s + (e.confidence || 0), 0) / entries.length
    : 0

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 px-6">
      <AICard label="Courbe d'apprentissage">
        <div className="text-xl font-mono font-bold text-slate-100">{currentWinRate}%</div>
        <div className="text-xs text-slate-500">{closed.length} trades clôturés</div>
        {tranches.length > 1 && (
          <div className="mt-2 h-12">
            <LearningCurve data={tranches} />
          </div>
        )}
      </AICard>

      <AICard label="Coût API">
        <div className="text-xl font-mono font-bold text-slate-100">${totalCost.toFixed(4)}</div>
        <div className="text-xs text-slate-500">
          {Object.entries(agentsCosts || {})
            .filter(([k]) => !k.startsWith('_'))
            .map(([k, v]) => `${k.split('_')[0]}: ${v.calls}`)
            .join(' / ')}
        </div>
      </AICard>

      <AICard label="Accord inter-agents">
        <div className="text-xl font-mono font-bold text-slate-100">{agreementPct}%</div>
        <div className="text-xs text-slate-500">sur {recentDecisions.length} dernières décisions</div>
      </AICard>

      <AICard label="Qualité mémoire">
        <div className="text-xl font-mono font-bold text-slate-100">{entries.length} leçons</div>
        <div className="text-xs text-slate-500">confiance moy: {avgConf.toFixed(2)}</div>
      </AICard>
    </div>
  )
}

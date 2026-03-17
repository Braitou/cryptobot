const verdictColors = {
  BUY: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  SELL: 'bg-red-500/20 text-red-400 border-red-500/30',
  WAIT: 'bg-slate-500/20 text-slate-400 border-slate-500/30',
  APPROVE: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  REDUCE: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  REJECT: 'bg-red-500/20 text-red-400 border-red-500/30',
}

function AgentBlock({ name, verdict, reasoning, thinking }) {
  return (
    <div className="border-b border-slate-800/50 last:border-b-0 py-3 px-4">
      <div className="flex items-center gap-2 mb-1.5">
        <span className="text-xs font-medium text-slate-300">{name}</span>
        {thinking ? (
          <span className="text-xs text-blue-400 animate-pulse">Raisonne...</span>
        ) : verdict ? (
          <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${verdictColors[verdict] || verdictColors.WAIT}`}>
            {verdict}
          </span>
        ) : null}
      </div>
      {reasoning ? (
        <p className="text-xs text-slate-400 leading-relaxed">{reasoning}</p>
      ) : !thinking ? (
        <p className="text-xs text-slate-600 italic">En attente du prochain signal</p>
      ) : null}
    </div>
  )
}

export default function AgentReasoning({ reasoning }) {
  const { analyst, decision, riskEval } = reasoning || {}

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
      <div className="px-4 py-2 border-b border-slate-800">
        <h3 className="text-sm font-medium text-slate-300">Raisonnement en cours</h3>
      </div>
      <AgentBlock
        name="Market Analyst"
        verdict={analyst?.regime}
        reasoning={analyst?.summary}
        thinking={analyst?.thinking}
      />
      <AgentBlock
        name="Decision Agent"
        verdict={decision?.action}
        reasoning={decision?.reasoning}
        thinking={decision?.thinking}
      />
      <AgentBlock
        name="Risk Evaluator"
        verdict={riskEval?.verdict}
        reasoning={riskEval?.reasoning}
        thinking={riskEval?.thinking}
      />
    </div>
  )
}

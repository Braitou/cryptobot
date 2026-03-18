const REGIME_COLORS = {
  RANGING: { bg: 'bg-blue-500', text: 'text-blue-400', label: 'Ranging' },
  TRENDING_UP: { bg: 'bg-emerald-500', text: 'text-emerald-400', label: 'Trend Up' },
  TRENDING_DOWN: { bg: 'bg-red-500', text: 'text-red-400', label: 'Trend Down' },
  HIGH_VOLATILITY: { bg: 'bg-orange-500', text: 'text-orange-400', label: 'High Vol' },
}

export default function RegimeBar({ currentRegime }) {
  // Pour l'instant, on affiche juste le régime actuel comme barre pleine
  // Quand on aura l'historique des changements, on segmentera la barre
  const regime = REGIME_COLORS[currentRegime] || REGIME_COLORS.RANGING

  return (
    <div>
      <h4 className="text-xs text-slate-400 mb-2">Regimes 24h</h4>
      <div className="h-4 rounded-full overflow-hidden bg-slate-800">
        <div className={`h-full ${regime.bg} rounded-full`} style={{ width: '100%' }} />
      </div>
      <div className="flex gap-3 mt-2">
        {Object.entries(REGIME_COLORS).map(([key, val]) => (
          <span key={key} className="flex items-center gap-1 text-[10px] text-slate-500">
            <span className={`w-2 h-2 rounded-sm ${val.bg} ${key === currentRegime ? 'opacity-100' : 'opacity-30'}`} />
            {val.label}
          </span>
        ))}
      </div>
    </div>
  )
}

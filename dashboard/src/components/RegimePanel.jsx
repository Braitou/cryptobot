const REGIME_STYLES = {
  RANGING: 'text-blue-400',
  TRENDING_UP: 'text-emerald-400',
  TRENDING_DOWN: 'text-red-400',
  HIGH_VOLATILITY: 'text-orange-400',
}

export default function RegimePanel({ config }) {
  if (!config) return null

  const regime = config.active_regime || 'RANGING'
  const preset = config.active_preset || {}
  const regimeInfo = config.regime_info || {}
  const lastChange = regimeInfo.last_change

  const scalpOn = preset.scalp_enabled
  const momentumOn = preset.momentum_enabled

  // Temps depuis le dernier changement
  let sinceText = ''
  if (lastChange) {
    const elapsed = (Date.now() - new Date(lastChange).getTime()) / 60000
    if (elapsed < 60) sinceText = `${Math.floor(elapsed)}min`
    else sinceText = `${Math.floor(elapsed / 60)}h ${Math.floor(elapsed % 60)}min`
  }

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
      <h3 className="text-xs text-slate-400 mb-2">Regime actuel</h3>

      <div className={`text-xl font-bold ${REGIME_STYLES[regime] || 'text-slate-300'}`}>
        {regime.replace('_', ' ')}
      </div>

      {sinceText && (
        <div className="text-xs text-slate-500 mt-1">
          Depuis {sinceText} — source: Python ADX
        </div>
      )}

      <div className="flex gap-2 mt-3">
        <span className={`text-xs px-2 py-0.5 rounded-full ${
          scalpOn
            ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
            : 'bg-slate-800 text-slate-500 border border-slate-700'
        }`}>
          Scalp {scalpOn ? 'ON' : 'OFF'}
        </span>
        <span className={`text-xs px-2 py-0.5 rounded-full ${
          momentumOn
            ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
            : 'bg-slate-800 text-slate-500 border border-slate-700'
        }`}>
          Momentum {momentumOn ? 'ON' : 'OFF'}
        </span>
      </div>

      {scalpOn && (
        <div className="mt-3 pt-3 border-t border-slate-800 text-xs text-slate-500 space-y-0.5">
          <div>RSI &le;{preset.scalp_rsi_threshold || 28} | BB &le;{preset.scalp_bb_threshold || 0.15}</div>
          <div>TP {preset.scalp_tp_atr_mult || 2}xATR | SL {preset.scalp_sl_atr_mult || 1}xATR</div>
          <div>Pos {preset.scalp_position_size_pct || 5}% | Max {preset.scalp_max_hold_minutes || 30}min</div>
        </div>
      )}
    </div>
  )
}

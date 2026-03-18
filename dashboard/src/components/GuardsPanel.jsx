function ProgressBar({ label, value, max, unit = '%' }) {
  const pct = max > 0 ? (value / max) * 100 : 0
  let barColor = 'bg-emerald-500'
  if (pct > 80) barColor = 'bg-red-500'
  else if (pct > 50) barColor = 'bg-orange-500'

  return (
    <div>
      <div className="flex justify-between text-xs mb-0.5">
        <span className="text-slate-500">{label}</span>
        <span className="text-slate-400 font-mono">{value.toFixed(1)}{unit} / {max}{unit}</span>
      </div>
      <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${barColor}`} style={{ width: `${Math.min(pct, 100)}%` }} />
      </div>
    </div>
  )
}

function Badge({ label, value, color = 'emerald' }) {
  const colors = {
    emerald: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
    orange: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
    red: 'bg-red-500/20 text-red-400 border-red-500/30',
    slate: 'bg-slate-800 text-slate-400 border-slate-700',
  }
  return (
    <div className="flex justify-between items-center">
      <span className="text-xs text-slate-500">{label}</span>
      <span className={`text-xs px-2 py-0.5 rounded-full border ${colors[color] || colors.slate}`}>
        {value}
      </span>
    </div>
  )
}

export default function GuardsPanel({ guards }) {
  if (!guards) return null

  const dailyLoss = guards.daily_loss_pct || 0
  const dailyMax = guards.daily_loss_max || 3
  const drawdown = guards.drawdown_pct || 0
  const drawdownMax = guards.drawdown_max || 15
  const corrExpo = guards.correlated_exposure_pct || 0
  const corrMax = guards.correlated_exposure_max || 15

  // Calendar
  const nextEvent = guards.next_event
  const calMult = guards.calendar_multiplier || 1.0
  let calText = 'Aucun'
  let calColor = 'emerald'
  if (nextEvent) {
    calText = `${nextEvent.name} ${nextEvent.hours_until.toFixed(0)}h`
    if (nextEvent.hours_until <= 2) { calColor = 'red' }
    else if (nextEvent.hours_until <= 6) { calColor = 'orange' }
  }
  if (calMult < 1) {
    calColor = calMult === 0 ? 'red' : 'orange'
    calText += ` (x${calMult})`
  }

  // Dead man's switch
  const lastUpdate = guards.config_meta_updated
  let deadManText = '--'
  let deadManColor = 'slate'
  if (lastUpdate) {
    const minAgo = Math.floor((Date.now() - new Date(lastUpdate).getTime()) / 60000)
    deadManText = `OK ${minAgo}min`
    deadManColor = minAgo > 360 ? 'red' : minAgo > 240 ? 'orange' : 'emerald'
  }

  const positions = guards.open_positions || 0
  const maxPos = guards.max_positions || 5

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
      <h3 className="text-xs text-slate-400 mb-3">Garde-fous</h3>
      <div className="space-y-2.5">
        <ProgressBar label="Perte jour" value={dailyLoss} max={dailyMax} />
        <ProgressBar label="Drawdown" value={drawdown} max={drawdownMax} />
        <ProgressBar label="Expo correlee" value={corrExpo} max={corrMax} />
      </div>
      <div className="border-t border-slate-800 mt-3 pt-3 space-y-2">
        <Badge label="Calendar" value={calText} color={calColor} />
        <Badge label="Dead man" value={deadManText} color={deadManColor} />
        <Badge label="Positions" value={`${positions} / ${maxPos}`} color={positions >= maxPos ? 'red' : 'emerald'} />
      </div>
    </div>
  )
}

const MIN_ATR_PCT = 0.40  // Seuil 0.40%
const MAX_ATR_DISPLAY = 0.60  // Max pour la largeur de la barre

export default function AtrPanel({ signals }) {
  const pairs = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
      <h3 className="text-xs text-slate-400 mb-3">Volatilite ATR 5min</h3>
      <div className="space-y-2.5">
        {pairs.map(pair => {
          const info = signals?.[pair] || {}
          const price = info.price || 0
          const atr = info.orderbook?.atr_14 || 0
          // ATR en % du prix
          const atrPct = price > 0 ? (atr / price) * 100 : 0
          const widthPct = Math.min((atrPct / MAX_ATR_DISPLAY) * 100, 100)
          const thresholdPos = (MIN_ATR_PCT / MAX_ATR_DISPLAY) * 100

          let barColor = 'bg-slate-600'
          if (atrPct >= MIN_ATR_PCT) barColor = 'bg-emerald-500'
          else if (atrPct >= MIN_ATR_PCT * 0.875) barColor = 'bg-orange-500'

          return (
            <div key={pair}>
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-500 w-8 shrink-0">{pair.replace('USDT', '')}</span>
                <div className="flex-1 h-3 bg-slate-800 rounded-full overflow-hidden relative">
                  <div className={`h-full rounded-full ${barColor}`} style={{ width: `${widthPct}%` }} />
                  {/* Trait vertical au seuil */}
                  <div
                    className="absolute top-0 h-full w-px bg-slate-400 opacity-50"
                    style={{ left: `${thresholdPos}%` }}
                  />
                </div>
                <span className={`text-xs font-mono w-12 text-right ${atrPct >= MIN_ATR_PCT ? 'text-emerald-400' : 'text-slate-500'}`}>
                  {atrPct > 0 ? `${atrPct.toFixed(2)}%` : '--'}
                </span>
              </div>
            </div>
          )
        })}
      </div>
      <div className="text-[10px] text-slate-600 mt-2 text-center">| = seuil {MIN_ATR_PCT}%</div>
    </div>
  )
}

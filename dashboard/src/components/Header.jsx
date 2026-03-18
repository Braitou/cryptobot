import { useState, useEffect } from 'react'
import KillSwitch from './KillSwitch'

export default function Header({ config, killSwitch, livePrices, wsConnected, lastWsTime }) {
  const [elapsed, setElapsed] = useState(0)

  // Timer "maj il y a Xs"
  useEffect(() => {
    const interval = setInterval(() => {
      if (lastWsTime) {
        setElapsed(Math.floor((Date.now() - lastWsTime) / 1000))
      }
    }, 1000)
    return () => clearInterval(interval)
  }, [lastWsTime])

  const mode = config?.settings?.trading_mode || config?.trading_mode || 'paper'

  return (
    <header className="flex items-center justify-between px-6 py-3 border-b border-slate-800">
      <div className="flex items-center gap-4">
        <h1 className="text-xl font-bold tracking-tight">CryptoBot <span className="text-slate-500 text-sm font-normal">v4</span></h1>

        {/* Badge Shadow/Live */}
        <span className={`flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full ${
          mode === 'live'
            ? 'bg-orange-500/20 text-orange-400 border border-orange-500/30'
            : 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
        }`}>
          <span className={`w-1.5 h-1.5 rounded-full ${mode === 'live' ? 'bg-orange-400' : 'bg-emerald-400'} animate-pulse`} />
          {mode === 'live' ? 'Live' : 'Shadow'}
        </span>

        {/* Badge WS */}
        <span className={`flex items-center gap-1.5 text-xs font-medium px-2 py-1 rounded-full ${
          wsConnected
            ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
            : 'bg-red-500/20 text-red-400 border border-red-500/30'
        }`}>
          <span className={`w-1.5 h-1.5 rounded-full ${wsConnected ? 'bg-emerald-400 animate-pulse' : 'bg-red-400'}`} />
          WS
        </span>

        {/* Dernière mise à jour */}
        <span className="text-xs text-slate-500">
          maj il y a {elapsed}s
        </span>
      </div>

      {/* Prix live BTC, ETH, SOL au centre */}
      <div className="flex items-center gap-4">
        {livePrices && Object.entries(livePrices).map(([pair, info]) => {
          const symbol = pair.replace('USDT', '')
          if (!['BTC', 'ETH', 'SOL'].includes(symbol)) return null
          const dirUp = info.direction === 'up'
          const dirDown = info.direction === 'down'
          return (
            <span key={pair} className="flex items-center gap-1.5 text-xs">
              <span className="text-slate-500">{symbol}</span>
              <span className={`font-mono ${dirUp ? 'text-emerald-400' : dirDown ? 'text-red-400' : 'text-slate-300'}`}>
                ${info.price?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
            </span>
          )
        })}
      </div>

      <KillSwitch killSwitch={killSwitch} />
    </header>
  )
}

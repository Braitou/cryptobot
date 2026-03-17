import KillSwitch from './KillSwitch'

export default function Header({ config, killSwitch, livePrices }) {
  const mode = config?.trading_mode || 'paper'
  const isLive = mode === 'live'

  return (
    <header className="flex items-center justify-between px-6 py-3 border-b border-slate-800">
      <div className="flex items-center gap-4">
        <h1 className="text-xl font-bold tracking-tight">CryptoBot</h1>
        <span className={`flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full ${
          isLive
            ? 'bg-orange-500/20 text-orange-400 border border-orange-500/30'
            : 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
        }`}>
          <span className={`w-1.5 h-1.5 rounded-full ${isLive ? 'bg-orange-400' : 'bg-emerald-400'} animate-pulse`} />
          {isLive ? 'Live trading' : 'Paper trading'}
        </span>
        {config?.testnet && (
          <span className="text-xs text-slate-500">testnet</span>
        )}
        {livePrices && Object.entries(livePrices).map(([pair, info]) => {
          const dirUp = info.direction === 'up'
          const dirDown = info.direction === 'down'
          return (
            <span key={pair} className="flex items-center gap-1.5 text-xs">
              <span className="text-slate-500">{pair.replace('USDT', '')}</span>
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

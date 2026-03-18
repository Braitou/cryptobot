const SOURCE_STYLES = {
  regime_advisor: { label: 'Regime Advisor', color: 'text-purple-400' },
  post_trade_logger: { label: 'Post-Trade', color: 'text-blue-400' },
  regime_detector: { label: 'Regime Detect', color: 'text-cyan-400' },
  news_scraper: { label: 'News', color: 'text-slate-400' },
}

const ACTION_BADGES = {
  HOLD: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  CONFIRM: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  OVERRIDE_REGIME: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  ADJUST_MULTIPLIER: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  REDUCE: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  PAUSE: 'bg-red-500/20 text-red-400 border-red-500/30',
  tag_trade: 'bg-slate-700 text-slate-300 border-slate-600',
  advise: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
}

function parseAction(entry) {
  // Essayer d'extraire l'action depuis la réponse JSON
  try {
    if (entry.response_received) {
      const data = JSON.parse(entry.response_received)
      return data.action || entry.action || '?'
    }
  } catch { /* ignore */ }
  return entry.action || '?'
}

function parseSummary(entry) {
  try {
    if (entry.response_received) {
      const data = JSON.parse(entry.response_received)
      return data.reasoning || data.notable_fact || JSON.stringify(data.tags || []).slice(0, 60)
    }
  } catch { /* ignore */ }
  return entry.response_received?.slice(0, 60) || '--'
}

export default function AIFeed({ aiFeed }) {
  const entries = aiFeed || []

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
      <div className="px-4 py-2 border-b border-slate-800 flex items-center gap-2">
        <h3 className="text-sm font-medium text-slate-300">Cerveau IA</h3>
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
      </div>
      <div className="max-h-[300px] overflow-y-auto">
        {entries.length === 0 ? (
          <div className="p-4 text-xs text-slate-500">Aucune activite IA</div>
        ) : (
          <div className="divide-y divide-slate-800/50">
            {entries.map((entry, i) => {
              const source = SOURCE_STYLES[entry.agent] || { label: entry.agent, color: 'text-slate-400' }
              const action = parseAction(entry)
              const badgeStyle = ACTION_BADGES[action] || ACTION_BADGES.tag_trade
              const summary = parseSummary(entry)
              const time = entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString('fr', { hour: '2-digit', minute: '2-digit' }) : ''

              return (
                <div key={i} className="px-3 py-2 flex items-start gap-2">
                  <span className="text-[10px] text-slate-600 font-mono w-10 shrink-0 pt-0.5">{time}</span>
                  <span className={`text-[10px] font-medium w-20 shrink-0 pt-0.5 ${source.color}`}>
                    {source.label}
                  </span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded border shrink-0 ${badgeStyle}`}>
                    {action}
                  </span>
                  <span className="text-[10px] text-slate-400 truncate">{summary}</span>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

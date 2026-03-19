import { useState, useEffect } from 'react'

// ─── Regime Advisor Card ─────────────────────────────────────────────

const ACTION_CONFIG = {
  HOLD:              { icon: '\u{1F7E2}', label: 'HOLD',       bg: 'bg-emerald-500/10', border: 'border-emerald-500/30', text: 'text-emerald-400' },
  CONFIRM:           { icon: '\u{1F7E2}', label: 'CONFIRM',    bg: 'bg-emerald-500/10', border: 'border-emerald-500/30', text: 'text-emerald-400' },
  OVERRIDE_REGIME:   { icon: '\u{1F535}', label: 'OVERRIDE',   bg: 'bg-blue-500/10',    border: 'border-blue-500/30',    text: 'text-blue-400' },
  ADJUST_MULTIPLIER: { icon: '\u{1F7E1}', label: 'ADJUST',     bg: 'bg-amber-500/10',   border: 'border-amber-500/30',   text: 'text-amber-400' },
  PAUSE:             { icon: '\u{1F534}', label: 'PAUSE',       bg: 'bg-red-500/10',     border: 'border-red-500/30',     text: 'text-red-400' },
}

function extractJson(text) {
  if (!text) return null
  // Direct parse
  try { return JSON.parse(text) } catch { /* continue */ }
  // Extract from ```json ... ```
  const fenced = text.match(/```json\s*([\s\S]*?)```/)
  if (fenced) {
    try { return JSON.parse(fenced[1].trim()) } catch { /* continue */ }
  }
  // Extract first { ... last }
  const first = text.indexOf('{')
  const last = text.lastIndexOf('}')
  if (first !== -1 && last > first) {
    try { return JSON.parse(text.slice(first, last + 1)) } catch { /* continue */ }
  }
  return null
}

function parseEntry(entry) {
  return extractJson(entry.response_received)
}

function RegimeAdvisorCard({ entry }) {
  const data = parseEntry(entry)
  if (!data) return null

  const action = data.action || 'HOLD'
  const cfg = ACTION_CONFIG[action] || ACTION_CONFIG.HOLD
  const confidence = data.confidence ?? '?'
  const reasoning = data.reasoning || data.summary || ''
  const newsFactors = Array.isArray(data.news_factors) ? data.news_factors : []
  const time = entry.timestamp
    ? new Date(entry.timestamp).toLocaleTimeString('fr', { hour: '2-digit', minute: '2-digit' })
    : ''

  return (
    <div className={`p-3 rounded-lg border ${cfg.bg} ${cfg.border}`}>
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-2">
          <span className="text-base leading-none">{cfg.icon}</span>
          <span className={`text-xs font-bold ${cfg.text}`}>{cfg.label}</span>
          {data.position_multiplier != null && (
            <span className="text-[10px] text-slate-400 font-mono">mult={data.position_multiplier}</span>
          )}
          {data.regime_override && (
            <span className="text-[10px] bg-red-500/20 text-red-300 px-1.5 py-0.5 rounded border border-red-500/30">
              {data.regime_override}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-slate-500 font-mono">{time}</span>
          <span className={`text-[10px] font-bold ${confidence >= 70 ? 'text-emerald-400' : confidence >= 40 ? 'text-amber-400' : 'text-red-400'}`}>
            {confidence}%
          </span>
        </div>
      </div>
      {reasoning && (
        <p className="text-xs text-slate-400 italic leading-relaxed">"{reasoning}"</p>
      )}

      {newsFactors.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1.5">
          {newsFactors.map((f, i) => (
            <span key={i} className="text-[10px] px-1.5 py-0.5 rounded border bg-slate-700/50 text-slate-300 border-slate-600">
              {typeof f === 'string' ? f : f.factor || f.name || JSON.stringify(f)}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Post-Trade Card ─────────────────────────────────────────────────

const TAG_COLORS = {
  good_entry: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
  bad_entry: 'bg-red-500/20 text-red-300 border-red-500/30',
  good_exit: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
  bad_exit: 'bg-red-500/20 text-red-300 border-red-500/30',
  sl_hit: 'bg-red-500/20 text-red-300 border-red-500/30',
  tp_hit: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
  trailing_stop: 'bg-amber-500/20 text-amber-300 border-amber-500/30',
  timeout: 'bg-slate-500/20 text-slate-300 border-slate-500/30',
}

function PostTradeCard({ entry }) {
  const data = parseEntry(entry)
  if (!data) return null

  const tradeData = entry.data ? (typeof entry.data === 'string' ? (() => { try { return JSON.parse(entry.data) } catch { return {} } })() : entry.data) : {}
  const time = entry.timestamp
    ? new Date(entry.timestamp).toLocaleTimeString('fr', { hour: '2-digit', minute: '2-digit' })
    : ''

  const tags = Array.isArray(data.tags) ? data.tags : []
  const summary = data.notable_fact || data.reasoning || data.summary || ''
  const entryQ = data.entry_quality
  const exitQ = data.exit_quality

  return (
    <div className="p-3 rounded-lg border bg-blue-500/5 border-blue-500/20">
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-2">
          <span className="text-base leading-none">{'\u{1F4CA}'}</span>
          <span className="text-xs font-bold text-blue-400">Post-Trade</span>
          {tradeData.trade_id && (
            <span className="text-[10px] text-slate-400 font-mono">#{tradeData.trade_id}</span>
          )}
          {tradeData.pair && (
            <span className="text-[10px] text-slate-400 font-mono">{tradeData.pair}</span>
          )}
        </div>
        <span className="text-[10px] text-slate-500 font-mono">{time}</span>
      </div>

      {(entryQ != null || exitQ != null) && (
        <div className="flex gap-3 mb-1.5">
          {entryQ != null && (
            <span className="text-[10px] text-slate-400">
              Entry: <span className={`font-bold ${entryQ >= 7 ? 'text-emerald-400' : entryQ >= 4 ? 'text-amber-400' : 'text-red-400'}`}>{entryQ}/10</span>
            </span>
          )}
          {exitQ != null && (
            <span className="text-[10px] text-slate-400">
              Exit: <span className={`font-bold ${exitQ >= 7 ? 'text-emerald-400' : exitQ >= 4 ? 'text-amber-400' : 'text-red-400'}`}>{exitQ}/10</span>
            </span>
          )}
        </div>
      )}

      {tags.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-1.5">
          {tags.map((tag, i) => (
            <span key={i} className={`text-[10px] px-1.5 py-0.5 rounded border ${TAG_COLORS[tag] || 'bg-slate-700/50 text-slate-300 border-slate-600'}`}>
              {tag}
            </span>
          ))}
        </div>
      )}

      {summary && (
        <p className="text-xs text-slate-400 italic leading-relaxed">"{summary}"</p>
      )}
    </div>
  )
}

// ─── Veille Marche ───────────────────────────────────────────────────

function FearGreedGauge({ value, label }) {
  const color = value <= 25 ? 'text-red-400' : value <= 45 ? 'text-orange-400' : value <= 55 ? 'text-slate-300' : value <= 75 ? 'text-emerald-400' : 'text-emerald-300'
  const barColor = value <= 25 ? 'bg-red-500' : value <= 45 ? 'bg-orange-500' : value <= 55 ? 'bg-slate-400' : value <= 75 ? 'bg-emerald-500' : 'bg-emerald-400'

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-[10px] text-slate-500">Fear & Greed</span>
        <span className={`text-sm font-bold font-mono ${color}`}>{value}</span>
      </div>
      <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
        <div className={`h-full ${barColor} rounded-full transition-all`} style={{ width: `${value}%` }} />
      </div>
      <span className="text-[10px] text-slate-500 mt-0.5 block">{label}</span>
    </div>
  )
}

function VeilleMarche({ news }) {
  if (!news) return null

  const fg = news.fear_greed
  const funding = news.funding_rates || {}
  const headlines = news.headlines || []

  const hasFunding = Object.keys(funding).length > 0
  const hasData = fg || hasFunding || headlines.length > 0

  if (!hasData) return null

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
      <div className="px-4 py-2 border-b border-slate-800 flex items-center gap-2">
        <h3 className="text-sm font-medium text-slate-300">{'\u{1F4E1}'} Veille Marche</h3>
      </div>
      <div className="p-3 space-y-3">
        {/* Fear & Greed */}
        {fg && <FearGreedGauge value={fg.value} label={fg.label} />}

        {/* Funding rates */}
        {hasFunding && (
          <div>
            <span className="text-[10px] text-slate-500 block mb-1">Funding Rates</span>
            <div className="flex gap-3">
              {Object.entries(funding).map(([pair, rate]) => (
                <div key={pair} className="text-[10px] font-mono">
                  <span className="text-slate-500">{pair.replace('USDT', '')}</span>{' '}
                  <span className={rate >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                    {rate >= 0 ? '+' : ''}{rate.toFixed(4)}%
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Headlines */}
        {headlines.length > 0 && (
          <div>
            <span className="text-[10px] text-slate-500 block mb-1">Headlines</span>
            <div className="space-y-1">
              {headlines.slice(0, 3).map((h, i) => (
                <div key={i} className="text-[10px] text-slate-400 leading-snug">
                  <span className="text-slate-600 mr-1">{h.source}</span>
                  {h.title}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Main Component ──────────────────────────────────────────────────

function FallbackCard({ entry }) {
  const time = entry.timestamp
    ? new Date(entry.timestamp).toLocaleTimeString('fr', { hour: '2-digit', minute: '2-digit' })
    : ''
  const agent = entry.agent || '?'
  const text = entry.response_received
    ? entry.response_received.slice(0, 200) + (entry.response_received.length > 200 ? '...' : '')
    : '--'

  return (
    <div className="p-3 rounded-lg border bg-slate-800/30 border-slate-700/50">
      <div className="flex items-center justify-between mb-1">
        <span className="text-[10px] font-bold text-slate-500">{agent}</span>
        <span className="text-[10px] text-slate-600 font-mono">{time}</span>
      </div>
      <p className="text-[10px] text-slate-500 break-all leading-relaxed">{text}</p>
    </div>
  )
}

function AICard({ entry }) {
  const data = parseEntry(entry)
  if (entry.agent === 'regime_advisor' && data) {
    return <RegimeAdvisorCard entry={entry} />
  }
  if (entry.agent === 'post_trade_logger' && data) {
    return <PostTradeCard entry={entry} />
  }
  return <FallbackCard entry={entry} />
}

export default function AIFeed({ aiFeed, news }) {
  const entries = aiFeed || []

  return (
    <div className="space-y-4">
      {/* Veille Marche */}
      <VeilleMarche news={news} />

      {/* Cerveau IA */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
        <div className="px-4 py-2 border-b border-slate-800 flex items-center gap-2">
          <h3 className="text-sm font-medium text-slate-300">{'\u{1F9E0}'} Cerveau IA</h3>
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
        </div>
        <div className="max-h-[400px] overflow-y-auto p-3 space-y-2">
          {entries.length === 0 ? (
            <div className="text-xs text-slate-500 py-2">Aucune activite IA</div>
          ) : (
            entries.slice(0, 15).map((entry, i) => (
              <AICard key={i} entry={entry} />
            ))
          )}
        </div>
      </div>
    </div>
  )
}

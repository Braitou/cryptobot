import { useEffect, useRef } from 'react'

// ─── Event type configs ──────────────────────────────────────────────

const EVENT_CONFIG = {
  // Heartbeats — discret
  candle: {
    label: 'Candle', icon: '\u{1F55B}',
    badge: 'bg-slate-700/40 text-slate-500 border-slate-600/30',
    text: 'text-slate-600', row: '', dim: true,
  },
  // Signals
  signal: {
    label: 'Signal', icon: '\u26A1',
    badge: 'bg-cyan-500/25 text-cyan-300 border-cyan-400/40',
    text: 'text-cyan-200', row: 'bg-cyan-500/[0.03]',
  },
  signal_filtered: {
    label: 'Filtered', icon: '\u{1F6AB}',
    badge: 'bg-slate-600/30 text-slate-400 border-slate-500/30',
    text: 'text-slate-400', row: '',
  },
  signal_blocked: {
    label: 'Blocked', icon: '\u{1F6E1}\uFE0F',
    badge: 'bg-orange-500/20 text-orange-300 border-orange-400/30',
    text: 'text-orange-300', row: 'bg-orange-500/[0.02]',
  },
  // Trades
  order_executed: {
    label: 'Trade Open', icon: '\u{1F4B0}',
    badge: 'bg-emerald-500/25 text-emerald-300 border-emerald-400/40',
    text: 'text-emerald-200', row: 'bg-emerald-500/[0.05]',
  },
  order_closed_win: {
    label: 'Trade Win', icon: '\u2705',
    badge: 'bg-emerald-500/30 text-emerald-300 border-emerald-400/50',
    text: 'text-emerald-200', row: 'bg-emerald-500/[0.05]',
  },
  order_closed_loss: {
    label: 'Trade Loss', icon: '\u274C',
    badge: 'bg-red-500/30 text-red-300 border-red-400/50',
    text: 'text-red-200', row: 'bg-red-500/[0.05]',
  },
  // Regime
  regime_change: {
    label: 'Regime', icon: '\u{1F504}',
    badge: 'bg-purple-500/25 text-purple-300 border-purple-400/40',
    text: 'text-purple-200', row: 'bg-purple-500/[0.04]',
  },
  // IA
  ia_regime_advisor: {
    label: 'IA Advisor', icon: '\u{1F9E0}',
    badge: 'bg-purple-500/25 text-purple-300 border-purple-400/40',
    text: 'text-purple-200', row: 'bg-purple-500/[0.03]',
  },
  trade_tagged: {
    label: 'Post-Trade', icon: '\u{1F3F7}\uFE0F',
    badge: 'bg-blue-500/20 text-blue-300 border-blue-400/30',
    text: 'text-blue-200', row: 'bg-blue-500/[0.02]',
  },
  // Thinking
  thinking: {
    label: 'Thinking', icon: '\u{1F4AD}',
    badge: 'bg-blue-500/20 text-blue-300 border-blue-400/30',
    text: 'text-blue-300', row: '',
  },
}

const DEFAULT_CONFIG = {
  label: 'Event', icon: '\u2139\uFE0F',
  badge: 'bg-slate-500/25 text-slate-300 border-slate-400/40',
  text: 'text-slate-200', row: '',
}

// ─── Filter reason labels ────────────────────────────────────────────

const FILTER_LABELS = {
  atr_low: 'ATR trop bas',
  micro_trend: 'Micro-trend contraire',
  regime_off: 'Regime inactif',
  correlation: 'Exposition correlee',
  risk_guard: 'Risk guard',
}

// ─── Helpers ─────────────────────────────────────────────────────────

function formatTime(ts) {
  if (!ts) return ''
  try {
    return new Date(ts).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return ''
  }
}

// ─── Event Row ───────────────────────────────────────────────────────

function FeedEvent({ event }) {
  const cfg = EVENT_CONFIG[event.eventType] || DEFAULT_CONFIG
  const isCandle = event.eventType === 'candle'
  const isThinking = event.eventType === 'thinking'

  return (
    <div className={`flex gap-3 py-2 px-4 ${cfg.row} ${isCandle ? 'opacity-30 hover:opacity-50' : 'hover:bg-white/[0.02]'} transition-opacity`}>
      {/* Timestamp */}
      <span className={`text-[11px] font-mono shrink-0 w-16 pt-0.5 ${isCandle ? 'text-slate-700' : 'text-slate-500'}`}>
        {formatTime(event.timestamp)}
      </span>

      {/* Badge + Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5 flex-wrap">
          <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border shrink-0 flex items-center gap-1 ${cfg.badge}`}>
            <span>{cfg.icon}</span> {cfg.label}
          </span>
          {event.pair && (
            <span className={`text-[10px] font-mono font-bold ${isCandle ? 'text-slate-600' : 'text-slate-400'}`}>
              {event.pair}
            </span>
          )}
          {event.badge && (
            <span className={`text-[10px] px-1.5 py-0.5 rounded border font-bold ${event.badgeStyle || 'bg-slate-700 text-slate-300 border-slate-600'}`}>
              {event.badge}
            </span>
          )}
        </div>

        {isThinking ? (
          <p className="text-sm text-blue-300 italic flex items-center gap-1.5">
            <span className="inline-block w-1.5 h-1.5 bg-blue-400 rounded-full animate-pulse" />
            <span className="inline-block w-1.5 h-1.5 bg-blue-400 rounded-full animate-pulse [animation-delay:150ms]" />
            <span className="inline-block w-1.5 h-1.5 bg-blue-400 rounded-full animate-pulse [animation-delay:300ms]" />
            <span className="ml-1">{event.text}</span>
          </p>
        ) : (
          <p className={`text-[12px] leading-relaxed ${cfg.text}`}>
            {event.text}
          </p>
        )}
      </div>
    </div>
  )
}

// ─── Main Component ──────────────────────────────────────────────────

export default function LiveFeed({ events }) {
  const containerRef = useRef(null)
  const wasAtBottom = useRef(true)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    if (wasAtBottom.current) {
      el.scrollTop = el.scrollHeight
    }
  }, [events.length])

  const handleScroll = () => {
    const el = containerRef.current
    if (!el) return
    wasAtBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40
  }

  // Count non-candle events
  const importantCount = events.filter(e => e.eventType !== 'candle').length

  return (
    <div className="bg-slate-950 border border-slate-800 rounded-lg flex flex-col" style={{ height: 'calc(100vh - 280px)', minHeight: '500px' }}>
      <div className="px-4 py-2.5 border-b border-slate-800 flex items-center justify-between shrink-0">
        <h3 className="text-sm font-medium text-slate-200">Live Feed</h3>
        <div className="flex items-center gap-3">
          {importantCount > 0 && (
            <span className="text-[10px] text-cyan-400 font-mono">{importantCount} events</span>
          )}
          <span className="text-[10px] text-slate-500 font-mono">{events.length} total</span>
        </div>
      </div>
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto divide-y divide-slate-800/20"
      >
        {events.length === 0 ? (
          <div className="flex items-center justify-center h-full text-sm text-slate-600 italic">
            En attente des premiers evenements...
          </div>
        ) : (
          events.map((event, i) => <FeedEvent key={i} event={event} />)
        )}
      </div>
    </div>
  )
}

export { FILTER_LABELS }

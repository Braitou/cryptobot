import { useEffect, useRef } from 'react'

// Badges agents — couleurs vives pour les badges
const agentStyles = {
  market_analyst:     { label: 'Market Analyst',  bg: 'bg-blue-500/25',    text: 'text-blue-300',    border: 'border-blue-400/40' },
  decision:           { label: 'Decision Agent',  bg: 'bg-emerald-500/25', text: 'text-emerald-300', border: 'border-emerald-400/40' },
  decision_agent:     { label: 'Decision Agent',  bg: 'bg-emerald-500/25', text: 'text-emerald-300', border: 'border-emerald-400/40' },
  risk_evaluator:     { label: 'Risk Evaluator',  bg: 'bg-orange-500/25',  text: 'text-orange-300',  border: 'border-orange-400/40' },
  risk_guard:         { label: 'Risk Guard',      bg: 'bg-red-500/25',     text: 'text-red-300',     border: 'border-red-400/40' },
  executor:           { label: 'Executor',        bg: 'bg-violet-500/25',  text: 'text-violet-300',  border: 'border-violet-400/40' },
  post_trade:         { label: 'Post-Trade',      bg: 'bg-pink-500/25',    text: 'text-pink-300',    border: 'border-pink-400/40' },
  post_trade_learner: { label: 'Post-Trade',      bg: 'bg-pink-500/25',    text: 'text-pink-300',    border: 'border-pink-400/40' },
  signal_analyzer:    { label: 'Signal',          bg: 'bg-cyan-500/25',    text: 'text-cyan-300',    border: 'border-cyan-400/40' },
  system:             { label: 'System',          bg: 'bg-slate-500/25',   text: 'text-slate-300',   border: 'border-slate-400/40' },
  candle:             { label: 'Heartbeat',       bg: 'bg-slate-700/40',   text: 'text-slate-500',   border: 'border-slate-600/30' },
}

// Couleur du texte de contenu par type d'agent
const contentColors = {
  candle:             'text-slate-600',         // gris discret — heartbeat
  signal_analyzer:    'text-cyan-200',          // cyan vif — signal détecté
  market_analyst:     'text-blue-200',          // bleu clair — analyse
  decision:           'text-emerald-200',       // vert clair — décision
  decision_agent:     'text-emerald-200',
  risk_evaluator:     'text-orange-200',        // orange clair — évaluation risque
  risk_guard:         'text-red-200',           // rouge clair — guard
  executor:           'text-violet-200',        // violet clair — exécution
  post_trade:         'text-pink-200',          // rose clair — leçon
  post_trade_learner: 'text-pink-200',
  system:             'text-slate-200',
}

// Verdict badges — très visibles
const verdictStyles = {
  BUY:     'bg-emerald-500/30 text-emerald-300 border-emerald-400/50 font-bold',
  SELL:    'bg-red-500/30 text-red-300 border-red-400/50 font-bold',
  WAIT:    'bg-slate-500/30 text-slate-200 border-slate-400/40 font-bold',
  APPROVE: 'bg-emerald-500/30 text-emerald-300 border-emerald-400/50 font-bold',
  REDUCE:  'bg-yellow-500/30 text-yellow-300 border-yellow-400/50 font-bold',
  REJECT:  'bg-red-500/30 text-red-300 border-red-400/50 font-bold',
}

// Couleur de fond de la ligne entière (subtile) pour distinguer les types
const rowBg = {
  candle:          '',
  signal_analyzer: 'bg-cyan-500/[0.03]',
  market_analyst:  'bg-blue-500/[0.03]',
  decision:        'bg-emerald-500/[0.03]',
  decision_agent:  'bg-emerald-500/[0.03]',
  risk_evaluator:  'bg-orange-500/[0.03]',
  risk_guard:      'bg-red-500/[0.05]',
  executor:        'bg-violet-500/[0.05]',
  post_trade:      'bg-pink-500/[0.03]',
  post_trade_learner: 'bg-pink-500/[0.03]',
}

function formatTime(ts) {
  if (!ts) return ''
  try {
    const d = new Date(ts)
    return d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return ''
  }
}

function AgentBadge({ agent }) {
  const style = agentStyles[agent] || agentStyles.system
  return (
    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border shrink-0 ${style.bg} ${style.text} ${style.border}`}>
      {style.label}
    </span>
  )
}

function VerdictBadge({ verdict }) {
  if (!verdict) return null
  const style = verdictStyles[verdict] || verdictStyles.WAIT
  return (
    <span className={`text-[10px] px-2 py-0.5 rounded border ${style}`}>
      {verdict}
    </span>
  )
}

function FeedEvent({ event }) {
  const isCandle = event.agent === 'candle'
  const isThinking = event.type === 'thinking'
  const textColor = contentColors[event.agent] || 'text-slate-200'
  const bg = rowBg[event.agent] || ''

  return (
    <div className={`flex gap-3 py-2.5 px-4 ${bg} ${isCandle ? 'opacity-35 hover:opacity-60' : 'hover:bg-white/[0.02]'} transition-opacity`}>
      {/* Timestamp */}
      <span className={`text-[11px] font-mono shrink-0 w-16 pt-0.5 ${isCandle ? 'text-slate-700' : 'text-slate-500'}`}>
        {formatTime(event.timestamp)}
      </span>

      {/* Badge + Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1 flex-wrap">
          <AgentBadge agent={event.agent} />
          {event.verdict && <VerdictBadge verdict={event.verdict} />}
          {event.pair && (
            <span className={`text-[10px] font-mono ${isCandle ? 'text-slate-600' : 'text-slate-400'}`}>{event.pair}</span>
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
          <p className={`text-[13px] leading-relaxed ${textColor}`}>
            {event.text}
          </p>
        )}
      </div>
    </div>
  )
}

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

  return (
    <div className="bg-slate-950 border border-slate-800 rounded-lg flex flex-col" style={{ height: 'calc(100vh - 280px)', minHeight: '500px' }}>
      <div className="px-4 py-2.5 border-b border-slate-800 flex items-center justify-between shrink-0">
        <h3 className="text-sm font-medium text-slate-200">Live Feed</h3>
        <span className="text-[10px] text-slate-500 font-mono">{events.length} événements</span>
      </div>
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto divide-y divide-slate-800/20"
      >
        {events.length === 0 ? (
          <div className="flex items-center justify-center h-full text-sm text-slate-600 italic">
            En attente des premiers événements...
          </div>
        ) : (
          events.map((event, i) => <FeedEvent key={i} event={event} />)
        )}
      </div>
    </div>
  )
}

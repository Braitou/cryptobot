import { useState, useCallback, useRef, useEffect } from 'react'
import usePortfolio from './hooks/usePortfolio'
import Header from './components/Header'
import MetricCards from './components/MetricCards'
import AIMetricCards from './components/AIMetricCards'
import PriceChart from './components/PriceChart'
import TradeHistory from './components/TradeHistory'
import AgentReasoning from './components/AgentReasoning'
import MemoryView from './components/MemoryView'
import AgentStatus from './components/AgentStatus'
import LiveFeed from './components/LiveFeed'

const MAX_FEED_EVENTS = 200

function wsMessageToFeedEvent(msg) {
  const ts = msg.timestamp || new Date().toISOString()
  const pair = msg.data?.pair || ''

  switch (msg.type) {
    case 'candle_closed':
      return {
        timestamp: ts, agent: 'candle', pair: msg.data?.pair,
        text: `${msg.data?.pair} ${msg.data?.interval} close=${msg.data?.close?.toFixed(2)}`,
      }

    case 'signal':
      return {
        timestamp: ts, agent: 'signal_analyzer', pair,
        text: `Signal ${pair} score ${msg.data?.score >= 0 ? '+' : ''}${msg.data?.score?.toFixed(3)} — lancement chaîne IA`,
      }

    case 'thinking':
      return {
        timestamp: ts, agent: msg.data?.agent || 'system', pair: msg.data?.pair,
        type: 'thinking',
        text: `${agentLabel(msg.data?.agent)} raisonne sur ${msg.data?.pair}...`,
      }

    case 'analysis_complete':
      return {
        timestamp: ts, agent: 'market_analyst', pair,
        verdict: msg.data?.market_regime?.toUpperCase(),
        text: msg.data?.summary || `Régime: ${msg.data?.market_regime} (force ${msg.data?.strength})`,
      }

    case 'decision_made':
      return {
        timestamp: ts, agent: 'decision', pair,
        verdict: msg.data?.action,
        text: msg.data?.reasoning || `Décision: ${msg.data?.action}`,
      }

    case 'risk_evaluated':
      return {
        timestamp: ts, agent: 'risk_evaluator', pair,
        verdict: msg.data?.verdict,
        text: msg.data?.reasoning || `Verdict: ${msg.data?.verdict}`,
      }

    case 'order_executed':
      return {
        timestamp: ts, agent: 'executor', pair: msg.data?.pair,
        text: `Trade #${msg.data?.trade_id} ouvert — ${msg.data?.side} ${msg.data?.pair} ${msg.data?.quantity} @ ${msg.data?.entry_price?.toFixed(2)} (SL=${msg.data?.stop_loss?.toFixed(2)} TP=${msg.data?.take_profit?.toFixed(2)})`,
      }

    case 'order_closed':
      return {
        timestamp: ts, agent: 'executor', pair: msg.data?.pair,
        verdict: msg.data?.pnl >= 0 ? 'APPROVE' : 'REJECT',
        text: `Trade #${msg.data?.trade_id} fermé — ${msg.data?.reason} — P&L ${msg.data?.pnl >= 0 ? '+' : ''}${msg.data?.pnl?.toFixed(4)} USDT (${msg.data?.pnl_pct >= 0 ? '+' : ''}${msg.data?.pnl_pct?.toFixed(2)}%)`,
      }

    case 'lesson_learned':
      return {
        timestamp: ts, agent: 'post_trade',
        text: `Leçon [${msg.data?.lesson?.category}] : ${msg.data?.lesson?.content || msg.data?.outcome_analysis || 'Nouvelle leçon apprise'}`,
      }

    default:
      return null
  }
}

function agentLabel(agent) {
  const labels = {
    market_analyst: 'Market Analyst',
    decision: 'Decision Agent',
    risk_evaluator: 'Risk Evaluator',
  }
  return labels[agent] || agent || 'Agent'
}

function getWsUrl() {
  return 'ws://' + window.location.host + '/ws/live'
}

export default function App() {
  const { portfolio, trades, memory, agentsCosts, agentsStatus, config, refetch } = usePortfolio()

  const [activeTab, setActiveTab] = useState('dashboard')
  const [lastPrice, setLastPrice] = useState(null)
  const [livePrices, setLivePrices] = useState({})
  const [reasoning, setReasoning] = useState({ analyst: null, decision: null, riskEval: null })
  const [feedEvents, setFeedEvents] = useState([])
  const [wsConnected, setWsConnected] = useState(false)

  // Charger l'historique du feed au démarrage + peupler les prix
  useEffect(() => {
    fetch('/api/feed')
      .then(r => r.ok ? r.json() : [])
      .then(events => {
        const converted = events.map(msg => wsMessageToFeedEvent(msg)).filter(Boolean)
        if (converted.length > 0) {
          setFeedEvents(converted)
        }
        // Extraire le dernier prix de chaque paire depuis l'historique
        const prices = {}
        for (const msg of events) {
          if (msg.type === 'candle_closed' && msg.data?.pair && msg.data?.close) {
            prices[msg.data.pair] = { price: msg.data.close, direction: null }
          }
        }
        if (Object.keys(prices).length > 0) {
          setLivePrices(prices)
        }
      })
      .catch(() => {})
  }, [])

  // Refs pour accéder aux dernières valeurs dans le callback WS sans re-render
  const refetchRef = useRef(refetch)
  useEffect(() => { refetchRef.current = refetch }, [refetch])

  // WebSocket — connexion unique, jamais recréée
  useEffect(() => {
    let ws = null
    let reconnectTimer = null

    function connect() {
      const url = getWsUrl()
      console.log('[WS] Connecting to', url)
      ws = new WebSocket(url)

      ws.onopen = () => {
        console.log('[WS] Connected')
        setWsConnected(true)
        if (reconnectTimer) {
          clearTimeout(reconnectTimer)
          reconnectTimer = null
        }
      }

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data)
          console.log('[WS] Message:', msg.type, msg.data?.pair || '')

          // Feed event
          const feedEvent = wsMessageToFeedEvent(msg)
          if (feedEvent) {
            setFeedEvents(prev => {
              const next = [...prev, feedEvent]
              return next.length > MAX_FEED_EVENTS ? next.slice(-MAX_FEED_EVENTS) : next
            })
          }

          // State updates
          switch (msg.type) {
            case 'candle_closed':
              if (msg.data?.close) {
                setLastPrice({
                  time: Math.floor((msg.data.open_time || Date.now()) / 1000),
                  open: msg.data.open,
                  high: msg.data.high,
                  low: msg.data.low,
                  close: msg.data.close,
                })
                if (msg.data.pair) {
                  setLivePrices(prev => {
                    const prevPrice = prev[msg.data.pair]?.price
                    const direction = prevPrice == null ? null : msg.data.close > prevPrice ? 'up' : msg.data.close < prevPrice ? 'down' : (prev[msg.data.pair]?.direction || null)
                    return {
                      ...prev,
                      [msg.data.pair]: { price: msg.data.close, direction },
                    }
                  })
                }
              }
              break

            case 'thinking':
              if (msg.data?.agent === 'market_analyst') {
                setReasoning(prev => ({ ...prev, analyst: { thinking: true } }))
              } else if (msg.data?.agent === 'decision') {
                setReasoning(prev => ({ ...prev, decision: { thinking: true } }))
              } else if (msg.data?.agent === 'risk_evaluator') {
                setReasoning(prev => ({ ...prev, riskEval: { thinking: true } }))
              }
              break

            case 'analysis_complete':
              setReasoning(prev => ({
                ...prev,
                analyst: { thinking: false, regime: msg.data?.market_regime, summary: msg.data?.summary },
              }))
              break

            case 'decision_made':
              setReasoning(prev => ({
                ...prev,
                decision: { thinking: false, action: msg.data?.action, reasoning: msg.data?.reasoning },
              }))
              break

            case 'risk_evaluated':
              setReasoning(prev => ({
                ...prev,
                riskEval: { thinking: false, verdict: msg.data?.verdict, reasoning: msg.data?.reasoning },
              }))
              break

            case 'order_executed':
            case 'order_closed':
            case 'lesson_learned':
              refetchRef.current()
              break
          }
        } catch (e) {
          console.error('[WS] Parse error:', e)
        }
      }

      ws.onclose = () => {
        console.log('[WS] Disconnected, reconnecting in 3s...')
        setWsConnected(false)
        ws = null
        reconnectTimer = setTimeout(connect, 3000)
      }

      ws.onerror = () => {
        ws.close()
      }
    }

    connect()

    return () => {
      if (reconnectTimer) clearTimeout(reconnectTimer)
      if (ws) ws.close()
    }
  }, []) // Empty deps — created once, never recreated

  // Populate reasoning from last agent activity on page load
  useEffect(() => {
    if (!agentsStatus || Object.keys(agentsStatus).length === 0) return

    const tryParse = (raw) => {
      if (!raw) return null
      try {
        return typeof raw === 'string' ? JSON.parse(raw) : raw
      } catch { return null }
    }

    const analystLog = agentsStatus.market_analyst?.last_activity
    const decisionLog = agentsStatus.decision_agent?.last_activity
    const riskLog = agentsStatus.risk_evaluator?.last_activity

    const newReasoning = { analyst: null, decision: null, riskEval: null }

    if (analystLog?.response_received) {
      const parsed = tryParse(analystLog.response_received)
      if (parsed) {
        newReasoning.analyst = {
          thinking: false,
          regime: parsed.market_regime,
          summary: parsed.summary,
        }
      }
    }
    if (decisionLog?.response_received) {
      const parsed = tryParse(decisionLog.response_received)
      if (parsed) {
        newReasoning.decision = {
          thinking: false,
          action: parsed.action,
          reasoning: parsed.reasoning,
        }
      }
    }
    if (riskLog?.response_received) {
      const parsed = tryParse(riskLog.response_received)
      if (parsed) {
        newReasoning.riskEval = {
          thinking: false,
          verdict: parsed.verdict,
          reasoning: parsed.reasoning,
        }
      }
    }

    if (newReasoning.analyst || newReasoning.decision || newReasoning.riskEval) {
      setReasoning(prev => ({
        analyst: prev.analyst || newReasoning.analyst,
        decision: prev.decision || newReasoning.decision,
        riskEval: prev.riskEval || newReasoning.riskEval,
      }))
    }
  }, [agentsStatus])

  return (
    <div className="min-h-screen flex flex-col">
      <Header config={config} killSwitch={portfolio?.kill_switch} livePrices={livePrices} />

      <main className="flex-1 flex flex-col gap-4 py-4">
        {/* Metric cards — always visible */}
        <MetricCards portfolio={portfolio} trades={trades} config={config} />
        <AIMetricCards trades={trades} agentsCosts={agentsCosts} memory={memory} />

        {/* Tab bar */}
        <div className="px-6 flex gap-1 border-b border-slate-800">
          <button
            onClick={() => setActiveTab('dashboard')}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
              activeTab === 'dashboard'
                ? 'text-slate-100 border-blue-500'
                : 'text-slate-500 border-transparent hover:text-slate-300'
            }`}
          >
            Dashboard
          </button>
          <button
            onClick={() => setActiveTab('feed')}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px flex items-center gap-2 ${
              activeTab === 'feed'
                ? 'text-slate-100 border-blue-500'
                : 'text-slate-500 border-transparent hover:text-slate-300'
            }`}
          >
            Live Feed
            {feedEvents.length > 0 && (
              <span className="text-[10px] bg-slate-700 text-slate-400 px-1.5 py-0.5 rounded-full">
                {feedEvents.length}
              </span>
            )}
          </button>
        </div>

        {/* Tab content */}
        {activeTab === 'dashboard' ? (
          <div className="px-6 grid grid-cols-1 lg:grid-cols-5 gap-4">
            <div className="lg:col-span-3 flex flex-col gap-4">
              <PriceChart prices={lastPrice} trades={trades} />
              <TradeHistory trades={trades} />
            </div>
            <div className="lg:col-span-2 flex flex-col gap-4">
              <AgentReasoning reasoning={reasoning} />
              <MemoryView memory={memory} />
            </div>
          </div>
        ) : (
          <div className="px-6">
            <LiveFeed events={feedEvents} />
          </div>
        )}
      </main>

      <AgentStatus agentsStatus={agentsStatus} wsConnected={wsConnected} />
    </div>
  )
}

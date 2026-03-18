import { useState, useRef, useEffect } from 'react'
import usePortfolio from './hooks/usePortfolio'
import Header from './components/Header'
import MetricCards from './components/MetricCards'
import EquityCurve from './components/EquityCurve'
import RegimeBar from './components/RegimeBar'
import PairWinRate from './components/PairWinRate'
import RegimePanel from './components/RegimePanel'
import AtrPanel from './components/AtrPanel'
import SignalStats from './components/SignalStats'
import GuardsPanel from './components/GuardsPanel'
import OpenPositions from './components/OpenPositions'
import TradeHistory from './components/TradeHistory'
import AIFeed from './components/AIFeed'
import LiveFeed from './components/LiveFeed'
import KillSwitch from './components/KillSwitch'

const MAX_FEED_EVENTS = 200

function wsMessageToFeedEvent(msg) {
  const ts = msg.timestamp || new Date().toISOString()
  const pair = msg.data?.pair || ''

  switch (msg.type) {
    case 'candle_closed':
      return {
        timestamp: ts, agent: 'candle', pair,
        text: `${pair} ${msg.data?.interval} close=${msg.data?.close?.toFixed(2)}`,
      }
    case 'signal':
      return {
        timestamp: ts, agent: 'signal_analyzer', pair,
        text: `Signal ${pair} score ${msg.data?.score >= 0 ? '+' : ''}${msg.data?.score?.toFixed(3)}`,
      }
    case 'thinking':
      return {
        timestamp: ts, agent: msg.data?.agent || 'system', pair,
        type: 'thinking',
        text: `${msg.data?.agent || 'Agent'} raisonne sur ${pair}...`,
      }
    case 'decision_made':
      return {
        timestamp: ts, agent: 'decision', pair,
        verdict: msg.data?.action,
        text: msg.data?.reasoning || `Decision: ${msg.data?.action}`,
      }
    case 'order_executed':
      return {
        timestamp: ts, agent: 'executor', pair: msg.data?.pair,
        text: `Trade #${msg.data?.trade_id} ouvert -- ${msg.data?.side} ${msg.data?.pair} @ ${msg.data?.entry_price?.toFixed(2)}`,
      }
    case 'order_closed':
      return {
        timestamp: ts, agent: 'executor', pair: msg.data?.pair,
        verdict: msg.data?.pnl >= 0 ? 'APPROVE' : 'REJECT',
        text: `Trade #${msg.data?.trade_id} ferme -- ${msg.data?.reason} -- P&L ${msg.data?.pnl_pct >= 0 ? '+' : ''}${msg.data?.pnl_pct?.toFixed(2)}%`,
      }
    case 'regime_change':
      return {
        timestamp: ts, agent: 'regime_detector',
        text: `Regime: ${msg.data?.old} -> ${msg.data?.new}`,
      }
    case 'trade_tagged':
      return {
        timestamp: ts, agent: 'post_trade_logger',
        text: `Tags: ${(msg.data?.tags || []).join(', ')}`,
      }
    default:
      return null
  }
}

function getWsUrl() {
  return 'ws://' + window.location.host + '/ws/live'
}

export default function App() {
  const {
    portfolio, trades, agentsCosts, config,
    signalStats, guards, openPositions, aiFeed, signals,
    refetch,
  } = usePortfolio()

  const [activeTab, setActiveTab] = useState('dashboard')
  const [livePrices, setLivePrices] = useState({})
  const [feedEvents, setFeedEvents] = useState([])
  const [wsConnected, setWsConnected] = useState(false)
  const [lastWsTime, setLastWsTime] = useState(null)
  const [lastSignalTime, setLastSignalTime] = useState(null)

  const refetchRef = useRef(refetch)
  useEffect(() => { refetchRef.current = refetch }, [refetch])

  // Charger l'historique du feed + prix au démarrage
  useEffect(() => {
    fetch('/api/feed')
      .then(r => r.ok ? r.json() : [])
      .then(events => {
        const converted = events.map(msg => wsMessageToFeedEvent(msg)).filter(Boolean)
        if (converted.length > 0) setFeedEvents(converted)
        const prices = {}
        for (const msg of events) {
          if (msg.type === 'candle_closed' && msg.data?.pair && msg.data?.close) {
            prices[msg.data.pair] = { price: msg.data.close, direction: null }
          }
        }
        if (Object.keys(prices).length > 0) setLivePrices(prices)
      })
      .catch(() => {})
  }, [])

  // WebSocket
  useEffect(() => {
    let ws = null
    let reconnectTimer = null

    function connect() {
      ws = new WebSocket(getWsUrl())

      ws.onopen = () => {
        setWsConnected(true)
        if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
      }

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data)
          setLastWsTime(Date.now())

          const feedEvent = wsMessageToFeedEvent(msg)
          if (feedEvent) {
            setFeedEvents(prev => {
              const next = [...prev, feedEvent]
              return next.length > MAX_FEED_EVENTS ? next.slice(-MAX_FEED_EVENTS) : next
            })
          }

          switch (msg.type) {
            case 'candle_closed':
              if (msg.data?.close && msg.data?.pair) {
                setLivePrices(prev => {
                  const prevPrice = prev[msg.data.pair]?.price
                  const direction = prevPrice == null ? null : msg.data.close > prevPrice ? 'up' : msg.data.close < prevPrice ? 'down' : (prev[msg.data.pair]?.direction || null)
                  return { ...prev, [msg.data.pair]: { price: msg.data.close, direction } }
                })
              }
              break
            case 'signal':
              setLastSignalTime(Date.now())
              break
            case 'order_executed':
            case 'order_closed':
            case 'trade_tagged':
            case 'regime_change':
              refetchRef.current()
              break
          }
        } catch (e) {
          console.error('[WS] Parse error:', e)
        }
      }

      ws.onclose = () => {
        setWsConnected(false)
        ws = null
        reconnectTimer = setTimeout(connect, 3000)
      }
      ws.onerror = () => { ws.close() }
    }

    connect()
    return () => {
      if (reconnectTimer) clearTimeout(reconnectTimer)
      if (ws) ws.close()
    }
  }, [])

  const currentRegime = config?.active_regime || 'RANGING'

  return (
    <div className="min-h-screen flex flex-col">
      {/* Section 1 - Header */}
      <Header
        config={config}
        killSwitch={portfolio?.kill_switch}
        livePrices={livePrices}
        wsConnected={wsConnected}
        lastWsTime={lastWsTime}
      />

      <main className="flex-1 flex flex-col gap-4 py-4">
        {/* Section 2 - Métriques (6 cartes) */}
        <MetricCards portfolio={portfolio} trades={trades} agentCosts={agentsCosts} />

        {/* Tab bar */}
        <div className="px-6 flex gap-1 border-b border-slate-800">
          <button
            onClick={() => setActiveTab('dashboard')}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
              activeTab === 'dashboard'
                ? 'text-slate-100 border-blue-500'
                : 'text-slate-500 border-transparent hover:text-slate-300'
            }`}
          >Dashboard</button>
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

        {activeTab === 'dashboard' ? (
          <>
            {/* Section 3 - Graphiques (60/40) */}
            <div className="px-6 grid grid-cols-1 lg:grid-cols-5 gap-4">
              <div className="lg:col-span-3">
                <EquityCurve trades={trades} initialCapital={config?.settings?.initial_capital || 500} />
              </div>
              <div className="lg:col-span-2 flex flex-col gap-4">
                <RegimeBar currentRegime={currentRegime} />
                <PairWinRate trades={trades} />
              </div>
            </div>

            {/* Section 4 - Panneaux opérationnels (4 colonnes) */}
            <div className="px-6 grid grid-cols-2 lg:grid-cols-4 gap-3">
              <RegimePanel config={config} />
              <AtrPanel signals={signals} />
              <SignalStats stats={signalStats} lastSignalTime={lastSignalTime} />
              <GuardsPanel guards={guards} />
            </div>

            {/* Section 5 - Positions ouvertes (conditionnel) */}
            <OpenPositions positions={openPositions} />

            {/* Section 6 - Trades récents + Cerveau IA (60/40) */}
            <div className="px-6 grid grid-cols-1 lg:grid-cols-5 gap-4">
              <div className="lg:col-span-3">
                <TradeHistory trades={trades} />
              </div>
              <div className="lg:col-span-2">
                <AIFeed aiFeed={aiFeed} />
              </div>
            </div>
          </>
        ) : (
          <div className="px-6">
            <LiveFeed events={feedEvents} />
          </div>
        )}
      </main>
    </div>
  )
}

import { useEffect, useRef, useState, Component } from 'react'
import { createChart } from 'lightweight-charts'

class ChartErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false }
  }
  static getDerivedStateFromError() {
    return { hasError: true }
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-8 text-center">
          <p className="text-sm text-slate-500">Graphique temporairement indisponible</p>
          <button
            onClick={() => this.setState({ hasError: false })}
            className="mt-2 text-xs text-blue-400 hover:text-blue-300"
          >
            Réessayer
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

function PriceChartInner({ prices, trades }) {
  const containerRef = useRef(null)
  const chartRef = useRef(null)
  const seriesRef = useRef(null)
  const lastTimeRef = useRef(0)
  const [pair, setPair] = useState('BTCUSDT')

  // Create chart + load historical data
  useEffect(() => {
    if (!containerRef.current) return

    const chart = createChart(containerRef.current, {
      layout: {
        background: { color: '#0f172a' },
        textColor: '#94a3b8',
        fontSize: 11,
      },
      grid: {
        vertLines: { color: '#1e293b' },
        horzLines: { color: '#1e293b' },
      },
      crosshair: { mode: 0 },
      rightPriceScale: { borderColor: '#1e293b' },
      timeScale: {
        borderColor: '#1e293b',
        timeVisible: true,
        secondsVisible: false,
      },
      width: containerRef.current.clientWidth,
      height: 350,
    })

    const series = chart.addCandlestickSeries({
      upColor: '#10b981',
      downColor: '#ef4444',
      borderUpColor: '#10b981',
      borderDownColor: '#ef4444',
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
    })

    chartRef.current = chart
    seriesRef.current = series

    // Load historical candles
    fetch(`/api/candles/${pair}?interval=5m&limit=200`)
      .then(r => r.ok ? r.json() : [])
      .then(rows => {
        if (!rows.length || !seriesRef.current) return
        const data = rows
          .sort((a, b) => a.open_time - b.open_time)
          .map(c => ({
            time: Math.floor(c.open_time / 1000),
            open: c.open,
            high: c.high,
            low: c.low,
            close: c.close,
          }))
        seriesRef.current.setData(data)
        lastTimeRef.current = data[data.length - 1].time
        chart.timeScale().fitContent()
      })
      .catch(() => {})

    const resizeObserver = new ResizeObserver((entries) => {
      if (entries[0]) {
        const { width } = entries[0].contentRect
        if (width > 0) chart.applyOptions({ width })
      }
    })
    resizeObserver.observe(containerRef.current)

    return () => {
      resizeObserver.disconnect()
      chart.remove()
      chartRef.current = null
      seriesRef.current = null
    }
  }, [pair])

  // Live update from WebSocket
  useEffect(() => {
    if (!seriesRef.current || !prices) return
    try {
      const t = prices.time
      if (!t || !isFinite(t) || !isFinite(prices.open) || !isFinite(prices.close)) return
      if (t < lastTimeRef.current) return
      lastTimeRef.current = t
      seriesRef.current.update(prices)
    } catch {
      // ignore
    }
  }, [prices])

  // Trade markers
  useEffect(() => {
    if (!seriesRef.current || !trades?.length) return
    try {
      const markers = trades
        .filter(t => t.entry_time && t.entry_price && t.pair === pair)
        .map(t => ({
          time: Math.floor(new Date(t.entry_time).getTime() / 1000),
          position: t.side === 'BUY' ? 'belowBar' : 'aboveBar',
          color: t.side === 'BUY' ? '#10b981' : '#ef4444',
          shape: t.side === 'BUY' ? 'arrowUp' : 'arrowDown',
          text: `${t.side} ${t.pnl_pct != null ? (t.pnl_pct >= 0 ? '+' : '') + t.pnl_pct.toFixed(1) + '%' : ''}`,
        }))
        .sort((a, b) => a.time - b.time)

      seriesRef.current.setMarkers(markers)
    } catch {
      // ignore
    }
  }, [trades, pair])

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
      <div className="px-4 py-2 border-b border-slate-800 flex items-center gap-3">
        {['BTCUSDT', 'ETHUSDT'].map(p => (
          <button
            key={p}
            onClick={() => setPair(p)}
            className={`text-sm font-medium transition-colors ${
              pair === p ? 'text-slate-100' : 'text-slate-500 hover:text-slate-300'
            }`}
          >
            {p.replace('USDT', '/USDT')}
          </button>
        ))}
        <span className="text-xs text-slate-600 ml-auto">5m</span>
      </div>
      <div ref={containerRef} />
    </div>
  )
}

export default function PriceChart(props) {
  return (
    <ChartErrorBoundary>
      <PriceChartInner {...props} />
    </ChartErrorBoundary>
  )
}

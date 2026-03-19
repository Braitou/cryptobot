import { useState, useEffect, useCallback } from 'react'

const API = '/api'

export default function usePortfolio() {
  const [portfolio, setPortfolio] = useState(null)
  const [trades, setTrades] = useState([])
  const [agentsCosts, setAgentsCosts] = useState({})
  const [config, setConfig] = useState(null)
  const [signalStats, setSignalStats] = useState({})
  const [guards, setGuards] = useState(null)
  const [openPositions, setOpenPositions] = useState([])
  const [aiFeed, setAiFeed] = useState([])
  const [signals, setSignals] = useState({})
  const [news, setNews] = useState(null)

  const fetchAll = useCallback(async () => {
    try {
      const endpoints = [
        fetch(`${API}/portfolio`),
        fetch(`${API}/trades?limit=50`),
        fetch(`${API}/agents/costs`),
        fetch(`${API}/config`),
        fetch(`${API}/signal_stats`),
        fetch(`${API}/guards`),
        fetch(`${API}/open_positions`),
        fetch(`${API}/ai_feed?limit=30`),
        fetch(`${API}/signals`),
        fetch(`${API}/news_summary`),
      ]
      const [pRes, tRes, cRes, cfgRes, ssRes, gRes, opRes, aiRes, sigRes, newsRes] = await Promise.all(endpoints)

      if (pRes.ok) setPortfolio(await pRes.json())
      if (tRes.ok) setTrades(await tRes.json())
      if (cRes.ok) setAgentsCosts(await cRes.json())
      if (cfgRes.ok) setConfig(await cfgRes.json())
      if (ssRes.ok) setSignalStats(await ssRes.json())
      if (gRes.ok) setGuards(await gRes.json())
      if (opRes.ok) setOpenPositions(await opRes.json())
      if (aiRes.ok) setAiFeed(await aiRes.json())
      if (sigRes.ok) setSignals(await sigRes.json())
      if (newsRes.ok) setNews(await newsRes.json())
    } catch (e) {
      // backend not available yet
    }
  }, [])

  useEffect(() => {
    fetchAll()
    const interval = setInterval(fetchAll, 10000)
    return () => clearInterval(interval)
  }, [fetchAll])

  return {
    portfolio, trades, agentsCosts, config,
    signalStats, guards, openPositions, aiFeed, signals, news,
    refetch: fetchAll,
  }
}

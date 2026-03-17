import { useState, useEffect, useCallback } from 'react'

const API = '/api'

export default function usePortfolio() {
  const [portfolio, setPortfolio] = useState(null)
  const [trades, setTrades] = useState([])
  const [memory, setMemory] = useState({ entries: [], context: '' })
  const [agentsCosts, setAgentsCosts] = useState({})
  const [agentsStatus, setAgentsStatus] = useState({})
  const [config, setConfig] = useState(null)

  const fetchAll = useCallback(async () => {
    try {
      const [pRes, tRes, mRes, cRes, sRes, cfgRes] = await Promise.all([
        fetch(`${API}/portfolio`),
        fetch(`${API}/trades?limit=50`),
        fetch(`${API}/memory`),
        fetch(`${API}/agents/costs`),
        fetch(`${API}/agents/status`),
        fetch(`${API}/config`),
      ])
      if (pRes.ok) setPortfolio(await pRes.json())
      if (tRes.ok) setTrades(await tRes.json())
      if (mRes.ok) setMemory(await mRes.json())
      if (cRes.ok) setAgentsCosts(await cRes.json())
      if (sRes.ok) setAgentsStatus(await sRes.json())
      if (cfgRes.ok) setConfig(await cfgRes.json())
    } catch (e) {
      // backend not available yet
    }
  }, [])

  useEffect(() => {
    fetchAll()
    const interval = setInterval(fetchAll, 15000)
    return () => clearInterval(interval)
  }, [fetchAll])

  return { portfolio, trades, memory, agentsCosts, agentsStatus, config, refetch: fetchAll }
}

import { useEffect, useRef, useState } from 'react'

const WS_URL = import.meta.env.DEV
  ? `ws://${window.location.hostname}:8000/ws/live`
  : `ws://${window.location.host}/ws/live`
const RECONNECT_DELAY = 3000

export default function useWebSocket(onMessage) {
  const wsRef = useRef(null)
  const [connected, setConnected] = useState(false)
  const reconnectTimer = useRef(null)
  const onMessageRef = useRef(onMessage)

  // Toujours garder la dernière version du callback sans recréer la connexion
  useEffect(() => {
    onMessageRef.current = onMessage
  }, [onMessage])

  useEffect(() => {
    function connect() {
      if (wsRef.current?.readyState === WebSocket.OPEN) return

      const ws = new WebSocket(WS_URL)

      ws.onopen = () => {
        setConnected(true)
        if (reconnectTimer.current) {
          clearTimeout(reconnectTimer.current)
          reconnectTimer.current = null
        }
      }

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data)
          onMessageRef.current(msg)
        } catch (e) {
          // ignore malformed
        }
      }

      ws.onclose = () => {
        setConnected(false)
        wsRef.current = null
        reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY)
      }

      ws.onerror = () => {
        ws.close()
      }

      wsRef.current = ws
    }

    connect()
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      if (wsRef.current) wsRef.current.close()
    }
  }, [])

  return { connected }
}

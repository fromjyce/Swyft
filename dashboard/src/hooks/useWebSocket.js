import { useState, useEffect, useRef, useCallback } from 'react'

const API = 'http://localhost:8000'
const WS  = 'ws://localhost:8000/ws'

export function useWebSocket() {
  const [live, setLive]       = useState(null)
  const [connected, setConnected] = useState(false)
  const wsRef  = useRef(null)
  const timer  = useRef(null)

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return
    const ws = new WebSocket(WS)
    wsRef.current = ws

    ws.onopen  = () => setConnected(true)
    ws.onclose = () => {
      setConnected(false)
      timer.current = setTimeout(connect, 3000)
    }
    ws.onerror = () => ws.close()
    ws.onmessage = (e) => {
      try { setLive(JSON.parse(e.data)) } catch {}
    }
  }, [])

  useEffect(() => {
    connect()
    return () => {
      clearTimeout(timer.current)
      wsRef.current?.close()
    }
  }, [connect])

  return { live, connected }
}

// REST helpers
export async function fetchPeers()   { const r = await fetch(`${API}/peers`);            return r.json() }
export async function fetchPieces()  { const r = await fetch(`${API}/pieces`);           return r.json() }
export async function fetchThreats() { const r = await fetch(`${API}/security/threats`); return r.json() }
export async function peerAction(ip, port, action) {
  return fetch(`${API}/peers/action`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ip, port, action })
  })
}

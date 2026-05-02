import { useState } from 'react'
import { useWebSocket } from './hooks/useWebSocket'
import Sidebar from './components/Sidebar'
import Overview from './components/Overview'
import PeersPage from './components/PeersPage'
import PiecesPage from './components/PiecesPage'
import SwarmPage from './components/SwarmPage'
import SecurityPage from './components/SecurityPage'

export default function App() {
  const [page, setPage] = useState('overview')
  const { live, connected } = useWebSocket()

  const pages = { overview: Overview, peers: PeersPage, pieces: PiecesPage, swarm: SwarmPage, security: SecurityPage }
  const Page = pages[page] || Overview

  return (
    <div className="app-shell">
      <Sidebar current={page} onChange={setPage} connected={connected} live={live} />
      <div className="main-area">
        <TopBar live={live} connected={connected} />
        <div className="page-content">
          <Page live={live} />
        </div>
      </div>
    </div>
  )
}

function TopBar({ live, connected }) {
  const name = live?.status?.name || 'No active torrent'
  const prog = live?.status?.progress ?? 0
  const speed = live?.metrics?.download_speed_mbps ?? 0

  return (
    <header style={{
      height: 'var(--header-h)',
      borderBottom: '1px solid var(--border-dim)',
      display: 'flex',
      alignItems: 'center',
      padding: '0 24px',
      gap: 16,
      background: 'var(--bg-deep)',
      flexShrink: 0,
    }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)', marginBottom: 4 }}>
          ACTIVE TORRENT
        </div>
        <div style={{
          fontFamily: 'var(--font-ui)',
          fontWeight: 600,
          fontSize: 13,
          color: 'var(--text-primary)',
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
        }}>
          {name}
        </div>
      </div>
      {live?.status && (
        <div style={{ width: 200, flexShrink: 0 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)' }}>
              {(prog * 100).toFixed(1)}%
            </span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--cyan)' }}>
              {speed.toFixed(2)} MB/s
            </span>
          </div>
          <div className="progress-track">
            <div className="progress-fill" style={{ width: `${prog * 100}%` }} />
          </div>
        </div>
      )}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
        <div style={{
          width: 7, height: 7,
          borderRadius: '50%',
          background: connected ? 'var(--green)' : 'var(--red)',
          boxShadow: connected ? '0 0 6px var(--green)' : '0 0 6px var(--red)',
          animation: connected ? 'pulse-cyan 2s infinite' : 'none',
        }} />
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)' }}>
          {connected ? 'LIVE' : 'OFFLINE'}
        </span>
      </div>
    </header>
  )
}

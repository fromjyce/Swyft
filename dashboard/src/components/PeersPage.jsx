import { useEffect, useState, useMemo } from 'react'
import { fetchPeers, peerAction } from '../hooks/useWebSocket'

const COLS = [
  { key: 'ip',               label: 'IP ADDRESS',    mono: true },
  { key: 'port',             label: 'PORT',          mono: true },
  { key: 'latency_ms',       label: 'LATENCY (ms)',  mono: true, fmt: v => v != null ? v.toFixed(0) : '—' },
  { key: 'download_speed_mbps', label: 'SPEED (MB/s)', mono: true, fmt: v => v?.toFixed(3) ?? '—' },
  { key: 'reliability',      label: 'RELIABILITY',   mono: true, fmt: v => v != null ? `${(v * 100).toFixed(0)}%` : '—' },
  { key: 'pieces_received',  label: 'PIECES',        mono: true },
  { key: 'composite_score',  label: 'SCORE',         mono: true, fmt: v => v?.toFixed(3) ?? '—' },
  { key: 'trust_level',      label: 'TRUST' },
]

export default function PeersPage({ live }) {
  const [data, setData] = useState(null)
  const [sortKey, setSortKey] = useState('composite_score')
  const [sortDir, setSortDir] = useState(-1)
  const [filter, setFilter] = useState('')
  const [actionPeer, setActionPeer] = useState(null)

  useEffect(() => {
    fetchPeers().then(setData).catch(() => {})
    const id = setInterval(() => fetchPeers().then(setData).catch(() => {}), 3000)
    return () => clearInterval(id)
  }, [])

  const sorted = useMemo(() => {
    if (!data?.peers) return []
    let list = data.peers
    if (filter) list = list.filter(p => p.ip.includes(filter) || p.trust_level?.includes(filter))
    return [...list].sort((a, b) => {
      const av = a[sortKey] ?? -Infinity
      const bv = b[sortKey] ?? -Infinity
      return (av < bv ? -1 : av > bv ? 1 : 0) * sortDir
    })
  }, [data, sortKey, sortDir, filter])

  const handleSort = (key) => {
    if (key === sortKey) setSortDir(d => -d)
    else { setSortKey(key); setSortDir(-1) }
  }

  const handleAction = async (peer, action) => {
    await peerAction(peer.ip, peer.port, action)
    setActionPeer(null)
    fetchPeers().then(setData)
  }

  return (
    <div className="animate-in">
      <div className="page-header">
        <h1 className="page-title">PEERS</h1>
        <span className="page-subtitle">
          {data ? `${data.connected} CONNECTED / ${data.total} TOTAL` : 'LOADING...'}
        </span>
      </div>

      {/* Summary row */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
        {[
          ['TOTAL', data?.total ?? '—', 'var(--text-secondary)'],
          ['CONNECTED', data?.connected ?? '—', 'var(--cyan)'],
          ['TRUSTED', sorted.filter(p => p.trust_level === 'trusted').length, 'var(--green)'],
          ['SUSPICIOUS', sorted.filter(p => p.trust_level === 'suspicious').length, 'var(--orange)'],
          ['MALICIOUS', sorted.filter(p => p.trust_level === 'malicious').length, 'var(--red)'],
        ].map(([label, val, color]) => (
          <div key={label} className="card" style={{ padding: '10px 16px', minWidth: 100 }}>
            <div className="label-caps" style={{ marginBottom: 4 }}>{label}</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 20, color }}>{val}</div>
          </div>
        ))}
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center' }}>
          <input
            value={filter}
            onChange={e => setFilter(e.target.value)}
            placeholder="Filter by IP or trust…"
            style={{
              background: 'var(--bg-elevated)',
              border: '1px solid var(--border-dim)',
              color: 'var(--text-primary)',
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
              padding: '6px 12px',
              borderRadius: 2,
              outline: 'none',
              width: 220,
            }}
          />
        </div>
      </div>

      <div className="card" style={{ overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                {COLS.map(c => (
                  <th key={c.key} onClick={() => handleSort(c.key)}>
                    {c.label}
                    {sortKey === c.key && (
                      <span style={{ marginLeft: 4, color: 'var(--cyan)' }}>
                        {sortDir === -1 ? '↓' : '↑'}
                      </span>
                    )}
                  </th>
                ))}
                <th>ACTIONS</th>
              </tr>
            </thead>
            <tbody>
              {sorted.length === 0 && (
                <tr>
                  <td colSpan={COLS.length + 1} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 32 }}>
                    {data ? 'NO PEERS FOUND' : 'CONNECTING TO API…'}
                  </td>
                </tr>
              )}
              {sorted.map((peer, i) => (
                <PeerRow
                  key={`${peer.ip}:${peer.port}`}
                  peer={peer}
                  onAction={(action) => handleAction(peer, action)}
                  style={{ animationDelay: `${i * 20}ms` }}
                />
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function PeerRow({ peer, onAction }) {
  const trust = peer.trust_level || 'neutral'
  const badgeClass = `badge badge-${trust}`

  const latColor = peer.latency_ms == null ? 'var(--text-muted)'
    : peer.latency_ms < 100 ? 'var(--green)'
    : peer.latency_ms < 300 ? 'var(--yellow)'
    : 'var(--orange)'

  return (
    <tr>
      <td className="mono" style={{ color: 'var(--text-primary)' }}>{peer.ip}</td>
      <td className="mono">{peer.port}</td>
      <td className="mono" style={{ color: latColor }}>
        {peer.latency_ms != null ? peer.latency_ms.toFixed(0) : '—'}
      </td>
      <td className="mono" style={{ color: 'var(--cyan)' }}>
        {peer.download_speed_mbps?.toFixed(3) ?? '—'}
      </td>
      <td className="mono">
        <ReliabilityBar value={peer.reliability ?? 0} />
      </td>
      <td className="mono">{peer.pieces_received}</td>
      <td className="mono">{peer.composite_score?.toFixed(3) ?? '—'}</td>
      <td><span className={badgeClass}>{trust}</span></td>
      <td>
        <div style={{ display: 'flex', gap: 6 }}>
          <ActionBtn label="BAN" color="var(--red)" onClick={() => onAction('ban')} />
          <ActionBtn label="REMOVE" color="var(--text-muted)" onClick={() => onAction('remove')} />
        </div>
      </td>
    </tr>
  )
}

function ReliabilityBar({ value }) {
  const pct = Math.round(value * 100)
  const color = value > 0.8 ? 'var(--green)' : value > 0.5 ? 'var(--cyan)' : value > 0.3 ? 'var(--orange)' : 'var(--red)'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{ width: 50, height: 4, background: 'var(--bg-elevated)', borderRadius: 2, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 2 }} />
      </div>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color }}>{pct}%</span>
    </div>
  )
}

function ActionBtn({ label, color, onClick }) {
  return (
    <button
      onClick={onClick}
      style={{
        background: 'transparent',
        border: `1px solid ${color}44`,
        color,
        fontFamily: 'var(--font-display)',
        fontSize: 8,
        letterSpacing: '0.1em',
        padding: '3px 8px',
        borderRadius: 2,
        cursor: 'pointer',
        transition: 'all 0.15s',
      }}
      onMouseEnter={e => e.currentTarget.style.background = `${color}18`}
      onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
    >
      {label}
    </button>
  )
}

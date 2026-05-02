import { useEffect, useRef, useState } from 'react'
import SpeedChart from './SpeedChart'

const MAX_HIST = 60

export default function Overview({ live }) {
  const [speedHistory, setSpeedHistory] = useState([])

  useEffect(() => {
    const s = live?.metrics?.download_speed_mbps ?? 0
    setSpeedHistory(h => [...h.slice(-MAX_HIST + 1), s])
  }, [live])

  const st = live?.status ?? {}
  const mt = live?.metrics ?? {}
  const sw = live?.swarm ?? {}
  const th = live?.threats ?? {}

  const progress = st.progress ?? 0
  const speedMbps = mt.download_speed_mbps ?? 0
  const eta = mt.eta_seconds
  const totalThreats = Object.values(th).reduce((a, b) => a + b, 0)

  return (
    <div className="animate-in">
      <div className="page-header">
        <h1 className="page-title">OVERVIEW</h1>
        <span className="page-subtitle">REAL-TIME NETWORK TELEMETRY</span>
      </div>

      {/* Top stat row */}
      <div className="grid-4" style={{ marginBottom: 20 }}>
        <StatCard
          label="DOWNLOAD SPEED"
          value={`${speedMbps.toFixed(2)}`}
          unit="MB/s"
          accent="cyan"
          large
        />
        <StatCard
          label="PROGRESS"
          value={`${(progress * 100).toFixed(1)}`}
          unit="%"
          accent="teal"
          large
          sub={st.bytes_downloaded != null ? `${(st.bytes_downloaded / 1e9).toFixed(2)} / ${(st.total_size / 1e9).toFixed(2)} GB` : null}
        />
        <StatCard
          label="ACTIVE PEERS"
          value={st.peers_active ?? '—'}
          unit={st.peers_total ? `/ ${st.peers_total}` : ''}
          accent="green"
          large
        />
        <StatCard
          label="ETA"
          value={eta != null && eta !== Infinity ? formatEta(eta) : '—'}
          accent={totalThreats > 0 ? 'red' : 'cyan'}
          large
          sub={totalThreats > 0 ? `${totalThreats} THREAT${totalThreats !== 1 ? 'S' : ''} DETECTED` : 'NO THREATS'}
          subColor={totalThreats > 0 ? 'var(--red)' : 'var(--green-dim)'}
        />
      </div>

      {/* Progress bar + pieces */}
      <div className="grid-2" style={{ marginBottom: 20 }}>
        <div className="card card-glow-cyan" style={{ padding: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
            <span className="label-caps">DOWNLOAD PROGRESS</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--cyan)' }}>
              {st.pieces_done ?? 0} / {st.pieces_total ?? 0} PIECES
            </span>
          </div>
          <div className="progress-track" style={{ height: 8, marginBottom: 10 }}>
            <div className="progress-fill" style={{ width: `${progress * 100}%` }} />
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)' }}>
              {st.bytes_downloaded != null ? `${(st.bytes_downloaded / 1e6).toFixed(0)} MB downloaded` : '—'}
            </span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)' }}>
              {mt.elapsed_seconds != null ? `${formatEta(mt.elapsed_seconds)} elapsed` : ''}
            </span>
          </div>
        </div>

        <div className="card card-glow-cyan" style={{ padding: 20 }}>
          <div style={{ marginBottom: 10 }}>
            <span className="label-caps">NETWORK STATS</span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px 20px' }}>
            {[
              ['CONNECTIONS', st.connections ?? '—'],
              ['PEER CHURN/MIN', mt.peer_churn_per_min?.toFixed(1) ?? '—'],
              ['AVG PIECE LATENCY', mt.avg_piece_latency_s != null ? `${mt.avg_piece_latency_s.toFixed(2)}s` : '—'],
              ['SWARM CLUSTERS', sw.clusters ?? '—'],
            ].map(([label, val]) => (
              <div key={label}>
                <div className="label-caps" style={{ marginBottom: 2 }}>{label}</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 15, color: 'var(--text-primary)' }}>{val}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Speed chart */}
      <div className="card card-glow-cyan" style={{ padding: '18px 20px 14px', marginBottom: 20 }}>
        <div style={{ marginBottom: 10 }}>
          <span className="label-caps">DOWNLOAD SPEED — LAST 60 SECONDS</span>
        </div>
        <SpeedChart history={speedHistory} height={90} />
      </div>

      {/* Mini piece heatgrid */}
      {st.pieces_total > 0 && (
        <div className="card" style={{ padding: 20 }}>
          <div style={{ marginBottom: 12 }}>
            <span className="label-caps">PIECE COMPLETION GRID</span>
          </div>
          <MiniPieceGrid done={st.pieces_done ?? 0} total={st.pieces_total ?? 0} />
        </div>
      )}
    </div>
  )
}

function StatCard({ label, value, unit, accent, large, sub, subColor }) {
  const colors = {
    cyan: 'var(--cyan)',
    teal: 'var(--teal)',
    green: 'var(--green)',
    red: 'var(--red)',
  }
  const color = colors[accent] || 'var(--cyan)'
  const glowClass = accent === 'green' ? 'card-glow-green' : accent === 'red' ? 'card-glow-red' : 'card-glow-cyan'

  return (
    <div className={`card ${glowClass}`} style={{ padding: '18px 20px' }}>
      <div className="label-caps" style={{ marginBottom: 10 }}>{label}</div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 5 }}>
        <span style={{
          fontFamily: 'var(--font-mono)',
          fontSize: large ? 30 : 20,
          color,
          textShadow: `0 0 12px ${color}66`,
          lineHeight: 1,
        }}>
          {value}
        </span>
        {unit && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>
            {unit}
          </span>
        )}
      </div>
      {sub && (
        <div style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 10,
          color: subColor || 'var(--text-muted)',
          marginTop: 6,
        }}>
          {sub}
        </div>
      )}
    </div>
  )
}

function MiniPieceGrid({ done, total }) {
  const CELL = 8
  const GAP = 2
  const cols = Math.min(total, 80)
  const ratio = done / total

  return (
    <div style={{
      display: 'flex',
      flexWrap: 'wrap',
      gap: GAP,
    }}>
      {Array.from({ length: cols }, (_, i) => {
        const isDone = i / cols < ratio
        return (
          <div
            key={i}
            style={{
              width: CELL,
              height: CELL,
              borderRadius: 1,
              background: isDone ? 'var(--cyan)' : 'var(--bg-elevated)',
              boxShadow: isDone ? '0 0 3px rgba(0,200,255,0.4)' : 'none',
              transition: 'background 0.3s',
            }}
          />
        )
      })}
      {total > 80 && (
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-muted)', alignSelf: 'center', marginLeft: 4 }}>
          +{total - 80} more
        </span>
      )}
    </div>
  )
}

function formatEta(s) {
  if (!isFinite(s)) return '∞'
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = Math.floor(s % 60)
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${sec}s`
  return `${sec}s`
}

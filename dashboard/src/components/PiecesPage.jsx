import { useEffect, useState } from 'react'
import { fetchPieces } from '../hooks/useWebSocket'

const STATE_COLOR = {
  complete:    '#00c8ff',
  downloading: '#ffd600',
  pending:     '#ff8c00',
  missing:     '#1a2a45',
  failed:      '#ff2d55',
}

const STATE_LABEL = {
  complete:    'COMPLETE',
  downloading: 'DOWNLOADING',
  pending:     'PENDING',
  missing:     'MISSING',
  failed:      'FAILED',
}

export default function PiecesPage() {
  const [data, setData] = useState(null)
  const [hovered, setHovered] = useState(null)

  useEffect(() => {
    fetchPieces().then(setData).catch(() => {})
    const id = setInterval(() => fetchPieces().then(setData).catch(() => {}), 2000)
    return () => clearInterval(id)
  }, [])

  const pieces = data?.pieces ?? []
  const counts = pieces.reduce((acc, p) => {
    acc[p.state] = (acc[p.state] || 0) + 1
    return acc
  }, {})

  return (
    <div className="animate-in">
      <div className="page-header">
        <h1 className="page-title">PIECES</h1>
        <span className="page-subtitle">
          {data ? `${data.completed} / ${data.total} COMPLETE — ${data.progress?.toFixed(1)}%` : 'LOADING...'}
        </span>
      </div>

      {/* Legend + counts */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
        {Object.entries(STATE_COLOR).map(([state, color]) => (
          <div key={state} className="card" style={{ padding: '10px 16px', display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ width: 10, height: 10, borderRadius: 1, background: color, boxShadow: state !== 'missing' ? `0 0 6px ${color}88` : 'none' }} />
            <div>
              <div className="label-caps">{STATE_LABEL[state]}</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 16, color }}>
                {counts[state] ?? 0}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Bitmap */}
      <div className="card card-glow-cyan" style={{ padding: 20 }}>
        <div style={{ marginBottom: 14 }}>
          <span className="label-caps">PIECE BITMAP — HOVER FOR DETAILS</span>
        </div>
        {pieces.length === 0 ? (
          <div style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: 12, textAlign: 'center', padding: 40 }}>
            {data ? 'NO PIECE DATA' : 'LOADING…'}
          </div>
        ) : (
          <PieceBitmap pieces={pieces} onHover={setHovered} hovered={hovered} />
        )}
      </div>

      {/* Hover tooltip */}
      {hovered != null && pieces[hovered] && (
        <div className="card" style={{
          position: 'fixed',
          bottom: 24,
          right: 28,
          padding: '12px 18px',
          zIndex: 200,
          borderColor: 'var(--border-mid)',
          minWidth: 180,
        }}>
          <div className="label-caps" style={{ marginBottom: 6 }}>PIECE #{hovered}</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{
              width: 8, height: 8, borderRadius: 1,
              background: STATE_COLOR[pieces[hovered].state] || '#888'
            }} />
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: STATE_COLOR[pieces[hovered].state] || 'var(--text-secondary)' }}>
              {STATE_LABEL[pieces[hovered].state] || pieces[hovered].state}
            </span>
          </div>
          {pieces[hovered].retries > 0 && (
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--orange)', marginTop: 4 }}>
              RETRIES: {pieces[hovered].retries}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function PieceBitmap({ pieces, onHover, hovered }) {
  const CELL = 10
  const GAP = 2
  const COLS = Math.floor((window.innerWidth - 220 - 80) / (CELL + GAP))

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: `repeat(${COLS}, ${CELL}px)`,
      gap: GAP,
    }}>
      {pieces.map((piece, i) => {
        const color = STATE_COLOR[piece.state] || '#888'
        const isHov = hovered === i
        return (
          <div
            key={piece.index}
            onMouseEnter={() => onHover(i)}
            onMouseLeave={() => onHover(null)}
            title={`#${piece.index}: ${piece.state}`}
            style={{
              width: CELL,
              height: CELL,
              borderRadius: 1,
              background: color,
              opacity: isHov ? 1 : (piece.state === 'missing' ? 0.7 : 0.9),
              boxShadow: (isHov || piece.state === 'downloading')
                ? `0 0 5px ${color}cc`
                : piece.state === 'complete'
                ? `0 0 2px ${color}44`
                : 'none',
              transform: isHov ? 'scale(1.5)' : 'none',
              transition: 'transform 0.1s, box-shadow 0.1s',
              cursor: 'crosshair',
              zIndex: isHov ? 2 : 1,
              position: 'relative',
              animation: piece.state === 'downloading' ? 'pulse-cyan 1s infinite' : 'none',
            }}
          />
        )
      })}
    </div>
  )
}

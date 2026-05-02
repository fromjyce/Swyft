const NAV = [
  { id: 'overview', label: 'OVERVIEW',  icon: GridIcon },
  { id: 'peers',    label: 'PEERS',     icon: PeerIcon },
  { id: 'pieces',   label: 'PIECES',    icon: PieceIcon },
  { id: 'swarm',    label: 'SWARM',     icon: SwarmIcon },
  { id: 'security', label: 'SECURITY',  icon: ShieldIcon },
]

export default function Sidebar({ current, onChange, connected, live }) {
  const threats = Object.values(live?.threats ?? {}).reduce((a, b) => a + b, 0)
  const peers = live?.status?.peers_active ?? 0

  return (
    <aside style={{
      position: 'fixed',
      left: 0, top: 0, bottom: 0,
      width: 'var(--sidebar-w)',
      background: 'var(--bg-deep)',
      borderRight: '1px solid var(--border-dim)',
      display: 'flex',
      flexDirection: 'column',
      zIndex: 100,
    }}>
      {/* Logo */}
      <div style={{
        height: 'var(--header-h)',
        display: 'flex',
        alignItems: 'center',
        padding: '0 20px',
        borderBottom: '1px solid var(--border-dim)',
        gap: 10,
      }}>
        <LogoMark />
        <div>
          <div style={{
            fontFamily: 'var(--font-display)',
            fontSize: 16,
            fontWeight: 900,
            letterSpacing: '0.12em',
            color: 'var(--cyan)',
            textShadow: '0 0 16px rgba(0,200,255,0.5)',
          }}>
            SWYFT
          </div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 8, color: 'var(--text-muted)', letterSpacing: '0.1em' }}>
            P2P ANALYZER v0.1
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav style={{ flex: 1, padding: '16px 0' }}>
        {NAV.map(({ id, label, icon: Icon }) => {
          const active = id === current
          const hasBadge = id === 'security' && threats > 0
          const peerBadge = id === 'peers' && peers > 0
          return (
            <button
              key={id}
              onClick={() => onChange(id)}
              style={{
                width: '100%',
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: '11px 20px',
                background: active ? 'rgba(0,200,255,0.07)' : 'transparent',
                border: 'none',
                borderLeft: `2px solid ${active ? 'var(--cyan)' : 'transparent'}`,
                cursor: 'pointer',
                textAlign: 'left',
                transition: 'all 0.15s',
                position: 'relative',
              }}
              onMouseEnter={e => { if (!active) e.currentTarget.style.background = 'rgba(0,200,255,0.03)' }}
              onMouseLeave={e => { if (!active) e.currentTarget.style.background = 'transparent' }}
            >
              <Icon size={15} color={active ? 'var(--cyan)' : 'rgba(150,180,220,0.4)'} />
              <span style={{
                fontFamily: 'var(--font-display)',
                fontSize: 11,
                fontWeight: active ? 700 : 500,
                letterSpacing: '0.12em',
                color: active ? 'var(--cyan)' : 'var(--text-muted)',
              }}>
                {label}
              </span>
              {hasBadge && (
                <span style={{
                  marginLeft: 'auto',
                  background: 'var(--red)',
                  color: '#fff',
                  fontSize: 9,
                  fontFamily: 'var(--font-mono)',
                  fontWeight: 700,
                  padding: '1px 5px',
                  borderRadius: 2,
                  minWidth: 18,
                  textAlign: 'center',
                }}>
                  {threats}
                </span>
              )}
              {peerBadge && (
                <span style={{
                  marginLeft: 'auto',
                  background: 'rgba(0,200,255,0.15)',
                  color: 'var(--cyan)',
                  fontSize: 9,
                  fontFamily: 'var(--font-mono)',
                  padding: '1px 5px',
                  borderRadius: 2,
                }}>
                  {peers}
                </span>
              )}
            </button>
          )
        })}
      </nav>

      {/* Bottom status */}
      <div style={{
        padding: '14px 20px',
        borderTop: '1px solid var(--border-dim)',
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
      }}>
        <SidebarStat label="CONNECTIONS" value={live?.status?.connections ?? '—'} />
        <SidebarStat label="PIECES DONE" value={live?.status?.pieces_done != null
          ? `${live.status.pieces_done}/${live.status.pieces_total}` : '—'} />
        <SidebarStat label="UPTIME" value={
          live?.metrics?.elapsed_seconds != null
            ? formatDuration(live.metrics.elapsed_seconds)
            : '—'
        } />
      </div>
    </aside>
  )
}

function SidebarStat({ label, value }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <span style={{ fontFamily: 'var(--font-display)', fontSize: 8, letterSpacing: '0.15em', color: 'var(--text-muted)' }}>
        {label}
      </span>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)' }}>
        {value}
      </span>
    </div>
  )
}

function formatDuration(s) {
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = Math.floor(s % 60)
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${sec}s`
  return `${sec}s`
}

// SVG icons
function LogoMark() {
  return (
    <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
      <polygon points="14,2 26,8 26,20 14,26 2,20 2,8" stroke="#00c8ff" strokeWidth="1.5" fill="rgba(0,200,255,0.08)" />
      <polygon points="14,7 21,11 21,17 14,21 7,17 7,11" stroke="#00ffd5" strokeWidth="1" fill="rgba(0,255,213,0.05)" />
      <circle cx="14" cy="14" r="3" fill="#00c8ff" style={{ filter: 'blur(1px)' }} />
    </svg>
  )
}

function GridIcon({ size, color }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none">
      <rect x="1" y="1" width="6" height="6" stroke={color} strokeWidth="1.2" />
      <rect x="9" y="1" width="6" height="6" stroke={color} strokeWidth="1.2" />
      <rect x="1" y="9" width="6" height="6" stroke={color} strokeWidth="1.2" />
      <rect x="9" y="9" width="6" height="6" stroke={color} strokeWidth="1.2" />
    </svg>
  )
}

function PeerIcon({ size, color }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none">
      <circle cx="8" cy="5" r="2.5" stroke={color} strokeWidth="1.2" />
      <circle cx="2.5" cy="12" r="1.8" stroke={color} strokeWidth="1.2" />
      <circle cx="13.5" cy="12" r="1.8" stroke={color} strokeWidth="1.2" />
      <line x1="8" y1="7.5" x2="2.5" y2="10.2" stroke={color} strokeWidth="1" />
      <line x1="8" y1="7.5" x2="13.5" y2="10.2" stroke={color} strokeWidth="1" />
    </svg>
  )
}

function PieceIcon({ size, color }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none">
      <rect x="1" y="1" width="4" height="4" fill={color} opacity="0.8" />
      <rect x="6" y="1" width="4" height="4" fill={color} opacity="0.4" />
      <rect x="11" y="1" width="4" height="4" fill={color} opacity="0.8" />
      <rect x="1" y="6" width="4" height="4" fill={color} opacity="0.4" />
      <rect x="6" y="6" width="4" height="4" fill={color} opacity="0.8" />
      <rect x="11" y="6" width="4" height="4" fill={color} opacity="0.2" />
      <rect x="1" y="11" width="4" height="4" fill={color} opacity="0.8" />
      <rect x="6" y="11" width="4" height="4" fill={color} opacity="0.8" />
      <rect x="11" y="11" width="4" height="4" fill={color} opacity="0.4" />
    </svg>
  )
}

function SwarmIcon({ size, color }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none">
      <circle cx="8" cy="8" r="2" stroke={color} strokeWidth="1.2" />
      <circle cx="3" cy="4" r="1.2" fill={color} opacity="0.6" />
      <circle cx="13" cy="4" r="1.2" fill={color} opacity="0.6" />
      <circle cx="3" cy="12" r="1.2" fill={color} opacity="0.6" />
      <circle cx="13" cy="12" r="1.2" fill={color} opacity="0.6" />
      <line x1="8" y1="6" x2="3" y2="4" stroke={color} strokeWidth="0.8" opacity="0.5" />
      <line x1="8" y1="6" x2="13" y2="4" stroke={color} strokeWidth="0.8" opacity="0.5" />
      <line x1="8" y1="10" x2="3" y2="12" stroke={color} strokeWidth="0.8" opacity="0.5" />
      <line x1="8" y1="10" x2="13" y2="12" stroke={color} strokeWidth="0.8" opacity="0.5" />
    </svg>
  )
}

function ShieldIcon({ size, color }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none">
      <path d="M8 1.5 L14 4 L14 9 C14 12 11 14.5 8 15 C5 14.5 2 12 2 9 L2 4 Z"
        stroke={color} strokeWidth="1.2" fill="none" />
      <path d="M5.5 8 L7 9.5 L10.5 6" stroke={color} strokeWidth="1.2" strokeLinecap="round" />
    </svg>
  )
}

import ClusterBubble from './ClusterBubble'

const CLUSTER_COLORS = {
  fast:       { bg: 'rgba(0,255,213,0.08)',  border: 'rgba(0,255,213,0.3)',  text: '#00ffd5' },
  slow:       { bg: 'rgba(255,214,0,0.08)',  border: 'rgba(255,214,0,0.3)',  text: '#ffd600' },
  unreliable: { bg: 'rgba(255,45,85,0.08)',  border: 'rgba(255,45,85,0.3)',  text: '#ff2d55' },
  normal:     { bg: 'rgba(0,200,255,0.06)',  border: 'rgba(0,200,255,0.2)',  text: '#00c8ff' },
}

export default function SwarmPage({ live }) {
  const sw = live?.swarm ?? {}
  const clusters = sw.cluster_details ?? []

  return (
    <div className="animate-in">
      <div className="page-header">
        <h1 className="page-title">SWARM ANALYSIS</h1>
        <span className="page-subtitle">PEER CLUSTER DYNAMICS</span>
      </div>

      {/* Summary stats */}
      <div className="grid-4" style={{ marginBottom: 20 }}>
        {[
          ['TOTAL CLUSTERS',      sw.clusters ?? '—',             'var(--text-secondary)'],
          ['FAST CLUSTERS',       sw.fast_clusters ?? '—',        '#00ffd5'],
          ['SLOW CLUSTERS',       sw.slow_clusters ?? '—',        '#ffd600'],
          ['UNRELIABLE CLUSTERS', sw.unreliable_clusters ?? '—',  '#ff2d55'],
        ].map(([label, val, color]) => (
          <div key={label} className="card" style={{ padding: '16px 20px' }}>
            <div className="label-caps" style={{ marginBottom: 8 }}>{label}</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 28, color, lineHeight: 1 }}>{val}</div>
          </div>
        ))}
      </div>

      <div className="grid-2" style={{ marginBottom: 20, alignItems: 'start' }}>
        {/* Cluster cards */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div className="label-caps" style={{ padding: '0 2px' }}>CLUSTER DETAILS</div>
          {clusters.length === 0 && (
            <div className="card" style={{ padding: 32, textAlign: 'center', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
              NO CLUSTER DATA — WAITING FOR SWARM ANALYSIS…
            </div>
          )}
          {clusters.map(c => <ClusterCard key={c.id} cluster={c} />)}
        </div>

        {/* Bubble chart */}
        <div className="card card-glow-cyan" style={{ padding: 20 }}>
          <div className="label-caps" style={{ marginBottom: 14 }}>CLUSTER TOPOLOGY</div>
          {clusters.length > 0
            ? <ClusterBubble clusters={clusters} height={320} />
            : (
              <div style={{
                height: 320,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--text-muted)',
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
              }}>
                AWAITING CLUSTER DATA
              </div>
            )
          }
        </div>
      </div>
    </div>
  )
}

function ClusterCard({ cluster }) {
  const colors = CLUSTER_COLORS[cluster.label] || CLUSTER_COLORS.normal

  return (
    <div style={{
      background: colors.bg,
      border: `1px solid ${colors.border}`,
      borderRadius: 4,
      padding: '16px 20px',
      position: 'relative',
      overflow: 'hidden',
    }}>
      {/* Accent line */}
      <div style={{
        position: 'absolute',
        left: 0, top: 0, bottom: 0,
        width: 3,
        background: colors.text,
        boxShadow: `0 0 8px ${colors.text}`,
      }} />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
        <div>
          <div style={{
            fontFamily: 'var(--font-display)',
            fontSize: 14,
            fontWeight: 700,
            letterSpacing: '0.1em',
            color: colors.text,
            marginBottom: 2,
          }}>
            {cluster.label.toUpperCase()}
          </div>
          <div className="label-caps">CLUSTER {cluster.id}</div>
        </div>
        <div style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 24,
          color: colors.text,
          lineHeight: 1,
        }}>
          {cluster.peers}
          <span style={{ fontSize: 10, color: 'var(--text-muted)', marginLeft: 4 }}>PEERS</span>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
        <Metric label="LATENCY" value={`${cluster.avg_latency_ms?.toFixed(0)}ms`} color={
          cluster.avg_latency_ms < 100 ? 'var(--green)' :
          cluster.avg_latency_ms < 300 ? 'var(--yellow)' : 'var(--orange)'
        } />
        <Metric label="SPEED" value={`${cluster.avg_speed_mbps?.toFixed(2)} MB/s`} color={colors.text} />
        <Metric label="RELIABILITY" value={`${(cluster.avg_reliability * 100).toFixed(0)}%`} color={
          cluster.avg_reliability > 0.8 ? 'var(--green)' :
          cluster.avg_reliability > 0.5 ? 'var(--yellow)' : 'var(--red)'
        } />
      </div>
    </div>
  )
}

function Metric({ label, value, color }) {
  return (
    <div>
      <div className="label-caps" style={{ marginBottom: 3 }}>{label}</div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color }}>{value}</div>
    </div>
  )
}

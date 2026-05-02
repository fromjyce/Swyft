import { useEffect, useRef, useState } from 'react'
import { fetchThreats } from '../hooks/useWebSocket'
import * as d3 from 'd3'

const SEV_COLOR = (s) => {
  if (s >= 0.8) return '#ff2d55'
  if (s >= 0.5) return '#ff8c00'
  if (s >= 0.25) return '#ffd600'
  return '#00c8ff'
}

const SEV_LABEL = (s) => {
  if (s >= 0.8) return 'CRITICAL'
  if (s >= 0.5) return 'HIGH'
  if (s >= 0.25) return 'MEDIUM'
  return 'LOW'
}

const TYPE_LABELS = {
  bad_data:           'Bad Data',
  repeated_timeouts:  'Repeated Timeouts',
  anomalous_pattern:  'Anomalous Pattern',
  abnormal_upload:    'Abnormal Upload',
  high_latency_variance: 'Latency Variance',
}

export default function SecurityPage({ live }) {
  const [data, setData] = useState(null)

  useEffect(() => {
    fetchThreats().then(setData).catch(() => {})
    const id = setInterval(() => fetchThreats().then(setData).catch(() => {}), 5000)
    return () => clearInterval(id)
  }, [])

  const counts = data?.threat_counts ?? live?.threats ?? {}
  const recent = data?.recent ?? []
  const totalEvents = data?.total_events ?? 0

  return (
    <div className="animate-in">
      <div className="page-header">
        <h1 className="page-title">SECURITY</h1>
        <span className="page-subtitle">THREAT DETECTION & REPUTATION</span>
      </div>

      {/* Threat summary */}
      <div className="grid-4" style={{ marginBottom: 20 }}>
        <div className="card card-glow-red" style={{ padding: '16px 20px' }}>
          <div className="label-caps" style={{ marginBottom: 8 }}>TOTAL EVENTS</div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 30, color: 'var(--red)', lineHeight: 1 }}>
            {totalEvents}
          </div>
        </div>
        {Object.entries(counts).slice(0, 3).map(([type, count]) => (
          <div key={type} className="card" style={{ padding: '16px 20px' }}>
            <div className="label-caps" style={{ marginBottom: 8 }}>
              {TYPE_LABELS[type] || type.replace(/_/g, ' ').toUpperCase()}
            </div>
            <div style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 28,
              color: count > 0 ? 'var(--orange)' : 'var(--text-muted)',
              lineHeight: 1,
            }}>
              {count}
            </div>
          </div>
        ))}
      </div>

      <div className="grid-2" style={{ marginBottom: 20, alignItems: 'start' }}>
        {/* Bar chart */}
        <div className="card card-glow-red" style={{ padding: 20 }}>
          <div className="label-caps" style={{ marginBottom: 14 }}>THREAT TYPE BREAKDOWN</div>
          <ThreatBarChart counts={counts} />
        </div>

        {/* Threat indicator panel */}
        <div className="card" style={{ padding: 20 }}>
          <div className="label-caps" style={{ marginBottom: 14 }}>THREAT STATUS</div>
          <ThreatStatus counts={counts} />
        </div>
      </div>

      {/* Event log */}
      <div className="card" style={{ overflow: 'hidden' }}>
        <div style={{ padding: '16px 20px 12px', borderBottom: '1px solid var(--border-dim)', display: 'flex', justifyContent: 'space-between' }}>
          <span className="label-caps">RECENT THREAT EVENTS</span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)' }}>
            {recent.length} EVENTS
          </span>
        </div>
        <div style={{ maxHeight: 340, overflowY: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>TIMESTAMP</th>
                <th>PEER</th>
                <th>TYPE</th>
                <th>SEVERITY</th>
                <th>DETAILS</th>
              </tr>
            </thead>
            <tbody>
              {recent.length === 0 && (
                <tr>
                  <td colSpan={5} style={{ textAlign: 'center', color: 'var(--green)', padding: 32, fontFamily: 'var(--font-mono)', fontSize: 12 }}>
                    ✓ NO THREATS DETECTED
                  </td>
                </tr>
              )}
              {recent.map((ev, i) => (
                <ThreatRow key={i} event={ev} />
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function ThreatRow({ event }) {
  const color = SEV_COLOR(event.severity)
  const ts = new Date(event.timestamp * 1000).toLocaleTimeString()

  return (
    <tr>
      <td className="mono" style={{ color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{ts}</td>
      <td className="mono" style={{ color: 'var(--text-primary)' }}>{event.peer}</td>
      <td>
        <span style={{
          fontFamily: 'var(--font-display)',
          fontSize: 9,
          fontWeight: 600,
          letterSpacing: '0.1em',
          color: 'var(--text-secondary)',
        }}>
          {TYPE_LABELS[event.type] || event.type}
        </span>
      </td>
      <td>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{
            width: 6, height: 6, borderRadius: '50%',
            background: color,
            boxShadow: `0 0 5px ${color}`,
          }} />
          <span style={{
            fontFamily: 'var(--font-display)',
            fontSize: 9,
            fontWeight: 700,
            letterSpacing: '0.1em',
            color,
          }}>
            {SEV_LABEL(event.severity)}
          </span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)' }}>
            ({event.severity.toFixed(2)})
          </span>
        </div>
      </td>
      <td className="mono" style={{ color: 'var(--text-muted)', fontSize: 11 }}>{event.details}</td>
    </tr>
  )
}

function ThreatBarChart({ counts }) {
  const ref = useRef(null)

  useEffect(() => {
    if (!ref.current) return
    const el = ref.current
    const w = el.clientWidth
    const h = el.clientHeight
    const margin = { top: 8, right: 16, bottom: 40, left: 80 }
    const iw = w - margin.left - margin.right
    const ih = h - margin.top - margin.bottom

    d3.select(el).selectAll('*').remove()

    const entries = Object.entries(counts).filter(([, v]) => v >= 0)
    if (!entries.length) {
      const svg = d3.select(el).append('svg').attr('width', w).attr('height', h)
      svg.append('text')
        .attr('x', w / 2).attr('y', h / 2)
        .attr('text-anchor', 'middle')
        .attr('fill', 'rgba(150,180,220,0.3)')
        .attr('font-family', "'Orbitron', sans-serif")
        .attr('font-size', 10)
        .attr('letter-spacing', '0.1em')
        .text('NO THREATS')
      return
    }

    const svg = d3.select(el).append('svg').attr('width', w).attr('height', h)
    const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`)

    const maxVal = d3.max(entries, d => d[1]) || 1

    const y = d3.scaleBand().domain(entries.map(d => d[0])).range([0, ih]).padding(0.35)
    const x = d3.scaleLinear().domain([0, maxVal]).range([0, iw])

    // Grid
    g.append('g').selectAll('line')
      .data(x.ticks(4))
      .join('line')
      .attr('y1', 0).attr('y2', ih)
      .attr('x1', d => x(d)).attr('x2', d => x(d))
      .attr('stroke', 'rgba(0,200,255,0.06)')
      .attr('stroke-dasharray', '3,4')

    // Bars
    g.selectAll('rect')
      .data(entries)
      .join('rect')
      .attr('y', d => y(d[0]))
      .attr('x', 0)
      .attr('height', y.bandwidth())
      .attr('width', d => x(d[1]))
      .attr('fill', d => d[1] > 0 ? '#ff2d5555' : '#00c8ff22')
      .attr('stroke', d => d[1] > 0 ? '#ff2d55' : '#00c8ff44')
      .attr('stroke-width', 1)
      .attr('rx', 2)
      .attr('filter', d => d[1] > 0 ? 'drop-shadow(0 0 4px rgba(255,45,85,0.4))' : 'none')

    // Value labels
    g.selectAll('.val')
      .data(entries)
      .join('text')
      .attr('class', 'val')
      .attr('x', d => x(d[1]) + 6)
      .attr('y', d => y(d[0]) + y.bandwidth() / 2)
      .attr('dominant-baseline', 'middle')
      .attr('fill', d => d[1] > 0 ? '#ff2d55' : 'rgba(150,180,220,0.4)')
      .attr('font-family', "'Share Tech Mono', monospace")
      .attr('font-size', 12)
      .text(d => d[1])

    // Y axis labels
    g.append('g')
      .selectAll('text')
      .data(entries)
      .join('text')
      .attr('x', -6)
      .attr('y', d => y(d[0]) + y.bandwidth() / 2)
      .attr('dominant-baseline', 'middle')
      .attr('text-anchor', 'end')
      .attr('fill', 'rgba(150,180,220,0.5)')
      .attr('font-family', "'Orbitron', sans-serif")
      .attr('font-size', 8)
      .attr('letter-spacing', '0.06em')
      .text(d => (TYPE_LABELS[d[0]] || d[0]).toUpperCase().slice(0, 12))

  }, [counts])

  return <div ref={ref} style={{ width: '100%', height: 200 }} />
}

function ThreatStatus({ counts }) {
  const totalThreats = Object.values(counts).reduce((a, b) => a + b, 0)
  const isClean = totalThreats === 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Status indicator */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 14,
        padding: '16px 20px',
        background: isClean ? 'rgba(0,255,136,0.06)' : 'rgba(255,45,85,0.08)',
        border: `1px solid ${isClean ? 'rgba(0,255,136,0.2)' : 'rgba(255,45,85,0.25)'}`,
        borderRadius: 3,
      }}>
        <div style={{
          width: 14, height: 14,
          borderRadius: '50%',
          background: isClean ? 'var(--green)' : 'var(--red)',
          boxShadow: isClean ? '0 0 10px rgba(0,255,136,0.6)' : '0 0 10px rgba(255,45,85,0.6)',
          animation: 'pulse-cyan 2s infinite',
          flexShrink: 0,
        }} />
        <div>
          <div style={{
            fontFamily: 'var(--font-display)',
            fontSize: 13,
            fontWeight: 700,
            letterSpacing: '0.1em',
            color: isClean ? 'var(--green)' : 'var(--red)',
          }}>
            {isClean ? 'ALL CLEAR' : 'THREATS DETECTED'}
          </div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
            {isClean ? 'No malicious activity found' : `${totalThreats} threat event${totalThreats !== 1 ? 's' : ''} recorded`}
          </div>
        </div>
      </div>

      {/* Per-type status */}
      {Object.entries(counts).map(([type, count]) => (
        <div key={type} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{
              width: 6, height: 6, borderRadius: '50%',
              background: count > 0 ? 'var(--red)' : 'var(--green)',
              boxShadow: count > 0 ? '0 0 5px rgba(255,45,85,0.6)' : '0 0 5px rgba(0,255,136,0.6)',
            }} />
            <span style={{ fontFamily: 'var(--font-ui)', fontSize: 13, color: 'var(--text-secondary)' }}>
              {TYPE_LABELS[type] || type}
            </span>
          </div>
          <span style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 13,
            color: count > 0 ? 'var(--orange)' : 'var(--green-dim)',
          }}>
            {count}
          </span>
        </div>
      ))}
    </div>
  )
}

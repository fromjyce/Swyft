import { useEffect, useRef } from 'react'
import * as d3 from 'd3'

const CLUSTER_COLORS = {
  fast:        '#00ffd5',
  slow:        '#ffd600',
  unreliable:  '#ff2d55',
  normal:      '#00c8ff',
}

export default function ClusterBubble({ clusters, width = '100%', height = 320 }) {
  const ref = useRef(null)

  useEffect(() => {
    if (!ref.current || !clusters?.length) return
    const el = ref.current
    const w = el.clientWidth
    const h = el.clientHeight

    d3.select(el).selectAll('*').remove()

    const svg = d3.select(el)
      .append('svg')
      .attr('width', w)
      .attr('height', h)

    // Background grid
    const defs = svg.append('defs')
    const pat = defs.append('pattern')
      .attr('id', 'bubble-grid')
      .attr('width', 30).attr('height', 30)
      .attr('patternUnits', 'userSpaceOnUse')
    pat.append('path')
      .attr('d', 'M 30 0 L 0 0 0 30')
      .attr('fill', 'none')
      .attr('stroke', 'rgba(0,200,255,0.05)')
      .attr('stroke-width', 0.5)
    svg.append('rect').attr('width', w).attr('height', h).attr('fill', 'url(#bubble-grid)')

    // Scales
    const maxPeers = d3.max(clusters, d => d.peer_count) || 1
    const r = d3.scaleSqrt().domain([0, maxPeers]).range([18, 65])

    const nodes = clusters.map(c => ({
      ...c,
      r: r(c.peer_count),
      x: w / 2 + (Math.random() - 0.5) * 100,
      y: h / 2 + (Math.random() - 0.5) * 80,
    }))

    const sim = d3.forceSimulation(nodes)
      .force('center', d3.forceCenter(w / 2, h / 2).strength(0.3))
      .force('collision', d3.forceCollide(d => d.r + 12).strength(0.9))
      .force('charge', d3.forceManyBody().strength(-30))

    const g = svg.append('g')

    // Glow filter
    const filt = defs.append('filter').attr('id', 'bubble-glow')
    filt.append('feGaussianBlur').attr('stdDeviation', '4').attr('result', 'blur')
    const merge = filt.append('feMerge')
    merge.append('feMergeNode').attr('in', 'blur')
    merge.append('feMergeNode').attr('in', 'SourceGraphic')

    const circles = g.selectAll('g.bubble')
      .data(nodes)
      .join('g')
      .attr('class', 'bubble')
      .style('cursor', 'pointer')

    // Outer glow ring
    circles.append('circle')
      .attr('r', d => d.r + 6)
      .attr('fill', 'none')
      .attr('stroke', d => CLUSTER_COLORS[d.label] || '#00c8ff')
      .attr('stroke-width', 0.5)
      .attr('opacity', 0.25)

    // Main bubble
    circles.append('circle')
      .attr('r', d => d.r)
      .attr('fill', d => {
        const color = CLUSTER_COLORS[d.label] || '#00c8ff'
        return `${color}18`
      })
      .attr('stroke', d => CLUSTER_COLORS[d.label] || '#00c8ff')
      .attr('stroke-width', 1.5)
      .attr('filter', 'url(#bubble-glow)')

    // Label: cluster type
    circles.append('text')
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'middle')
      .attr('dy', -10)
      .attr('fill', d => CLUSTER_COLORS[d.label] || '#00c8ff')
      .attr('font-family', "'Orbitron', sans-serif")
      .attr('font-size', d => Math.max(7, d.r * 0.22))
      .attr('font-weight', 700)
      .attr('letter-spacing', '0.08em')
      .text(d => d.label.toUpperCase())

    // Peer count
    circles.append('text')
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'middle')
      .attr('dy', 6)
      .attr('fill', 'rgba(200,225,255,0.8)')
      .attr('font-family', "'Share Tech Mono', monospace")
      .attr('font-size', d => Math.max(9, d.r * 0.28))
      .text(d => d.peer_count)

    // Speed sub-label
    circles.append('text')
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'middle')
      .attr('dy', d => d.r * 0.5)
      .attr('fill', 'rgba(150,180,220,0.45)')
      .attr('font-family', "'Share Tech Mono', monospace")
      .attr('font-size', d => Math.max(6, d.r * 0.18))
      .text(d => `${d.avg_speed_mbps?.toFixed(1)} MB/s`)

    // Hover interaction
    circles
      .on('mouseenter', function(event, d) {
        d3.select(this).select('circle:nth-child(2)')
          .transition().duration(150)
          .attr('fill', `${CLUSTER_COLORS[d.label] || '#00c8ff'}30`)
          .attr('stroke-width', 2.5)
      })
      .on('mouseleave', function(event, d) {
        d3.select(this).select('circle:nth-child(2)')
          .transition().duration(150)
          .attr('fill', `${CLUSTER_COLORS[d.label] || '#00c8ff'}18`)
          .attr('stroke-width', 1.5)
      })

    sim.on('tick', () => {
      circles.attr('transform', d => `translate(${
        Math.max(d.r + 10, Math.min(w - d.r - 10, d.x))
      },${
        Math.max(d.r + 10, Math.min(h - d.r - 10, d.y))
      })`)
    })

    return () => sim.stop()
  }, [clusters])

  return <div ref={ref} style={{ width, height }} />
}

import { useEffect, useRef } from 'react'
import * as d3 from 'd3'

export default function SpeedChart({ history, width = '100%', height = 80 }) {
  const ref = useRef(null)

  useEffect(() => {
    if (!ref.current || !history?.length) return
    const el = ref.current
    const w = el.clientWidth
    const h = el.clientHeight
    const margin = { top: 8, right: 8, bottom: 18, left: 36 }
    const iw = w - margin.left - margin.right
    const ih = h - margin.top - margin.bottom

    d3.select(el).selectAll('*').remove()

    const svg = d3.select(el)
      .append('svg')
      .attr('width', w)
      .attr('height', h)

    const g = svg.append('g')
      .attr('transform', `translate(${margin.left},${margin.top})`)

    const x = d3.scaleLinear().domain([0, history.length - 1]).range([0, iw])
    const y = d3.scaleLinear().domain([0, d3.max(history) * 1.15 || 1]).range([ih, 0])

    // Grid lines
    g.append('g')
      .selectAll('line')
      .data(y.ticks(3))
      .join('line')
      .attr('x1', 0).attr('x2', iw)
      .attr('y1', d => y(d)).attr('y2', d => y(d))
      .attr('stroke', 'rgba(0,200,255,0.06)')
      .attr('stroke-dasharray', '3,4')

    // Area fill
    const area = d3.area()
      .x((_, i) => x(i))
      .y0(ih)
      .y1(d => y(d))
      .curve(d3.curveCatmullRom.alpha(0.5))

    const grad = svg.append('defs').append('linearGradient')
      .attr('id', 'speed-grad')
      .attr('x1', '0%').attr('y1', '0%')
      .attr('x2', '0%').attr('y2', '100%')
    grad.append('stop').attr('offset', '0%').attr('stop-color', '#00c8ff').attr('stop-opacity', 0.25)
    grad.append('stop').attr('offset', '100%').attr('stop-color', '#00c8ff').attr('stop-opacity', 0)

    g.append('path')
      .datum(history)
      .attr('fill', 'url(#speed-grad)')
      .attr('d', area)

    // Line
    const line = d3.line()
      .x((_, i) => x(i))
      .y(d => y(d))
      .curve(d3.curveCatmullRom.alpha(0.5))

    g.append('path')
      .datum(history)
      .attr('fill', 'none')
      .attr('stroke', '#00c8ff')
      .attr('stroke-width', 1.5)
      .attr('filter', 'drop-shadow(0 0 3px rgba(0,200,255,0.6))')
      .attr('d', line)

    // Current point
    const last = history[history.length - 1]
    g.append('circle')
      .attr('cx', x(history.length - 1))
      .attr('cy', y(last))
      .attr('r', 3)
      .attr('fill', '#00c8ff')
      .attr('filter', 'drop-shadow(0 0 4px rgba(0,200,255,0.9))')

    // Y axis ticks
    g.append('g')
      .selectAll('text')
      .data(y.ticks(3))
      .join('text')
      .attr('x', -4)
      .attr('y', d => y(d))
      .attr('text-anchor', 'end')
      .attr('dominant-baseline', 'middle')
      .attr('fill', 'rgba(150,180,220,0.4)')
      .attr('font-family', "'Share Tech Mono', monospace")
      .attr('font-size', 8)
      .text(d => d.toFixed(1))

    // X label
    g.append('text')
      .attr('x', iw / 2).attr('y', ih + 14)
      .attr('text-anchor', 'middle')
      .attr('fill', 'rgba(150,180,220,0.25)')
      .attr('font-family', "'Orbitron', sans-serif")
      .attr('font-size', 7)
      .attr('letter-spacing', '0.1em')
      .text('LAST 60s — MB/s')

  }, [history])

  return <div ref={ref} style={{ width, height }} />
}

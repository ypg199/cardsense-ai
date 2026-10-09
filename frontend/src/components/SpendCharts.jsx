/**
 * SpendCharts.jsx — interactive SVG charts for the Spend Analyser.
 *
 * No chart library: each chart is a small SVG with a hover layer and a
 * tooltip. Colours come from CSS variables set on .sa-root, so a category
 * keeps the same colour in every chart on the page.
 */
import { useEffect, useRef, useState } from 'react'

// ── Formatting ──────────────────────────────────────────────────────────────
const inr = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })
export const money = v => `₹${inr.format(Math.round(v))}`

export function compactMoney(v) {
  const a = Math.abs(v)
  if (a >= 1e7) return `₹${(v / 1e7).toFixed(1).replace(/\.0$/, '')}Cr`
  if (a >= 1e5) return `₹${(v / 1e5).toFixed(1).replace(/\.0$/, '')}L`
  if (a >= 1e3) return `₹${(v / 1e3).toFixed(a >= 1e4 ? 0 : 1).replace(/\.0$/, '')}k`
  return `₹${Math.round(v)}`
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
export function monthLabel(m, long = false) {
  const match = /^(\d{4})-(\d{2})$/.exec(m || '')
  if (!match) return m
  const name = MONTHS[Number(match[2]) - 1]
  return long ? `${name} ${match[1]}` : `${name} ’${match[1].slice(2)}`
}

export const catLabel = cat =>
  cat === 'other_group' ? 'Other' : cat.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())

// "Nice" axis maximum and ticks (1, 2, 2.5, 5 × 10^n)
function niceTicks(max, count = 4) {
  if (max <= 0) return [0]
  const raw = max / count
  const pow = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map(m => m * pow).find(s => s >= raw)
  const ticks = []
  for (let v = 0; v <= max + step * 0.999; v += step) ticks.push(v)
  return ticks
}

// Width of a container, kept up to date on resize
function useWidth() {
  const ref = useRef(null)
  const [width, setWidth] = useState(0)
  useEffect(() => {
    if (!ref.current) return
    const ro = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width))
    ro.observe(ref.current)
    return () => ro.disconnect()
  }, [])
  return [ref, width]
}

// ── Tooltip ─────────────────────────────────────────────────────────────────
function Tooltip({ tip, width }) {
  if (!tip) return null
  const left = Math.min(Math.max(tip.x + 14, 0), Math.max(width - 230, 0))
  return (
    <div className="sa-tip" style={{ left, top: tip.y }} role="status">
      {tip.content}
    </div>
  )
}

function TipRows({ title, rows, total }) {
  return (
    <>
      <div className="sa-tip-title">{title}</div>
      {rows.map(r => (
        <div key={r.key} className={`sa-tip-row${r.strong ? ' strong' : ''}`}>
          {r.color && <span className="sa-swatch" style={{ background: r.color }} />}
          <span className="sa-tip-label">{r.label}</span>
          <span className="sa-tip-value">{r.value}</span>
        </div>
      ))}
      {total && (
        <div className="sa-tip-row sa-tip-total">
          <span className="sa-tip-label">{total.label}</span>
          <span className="sa-tip-value">{total.value}</span>
        </div>
      )}
    </>
  )
}

// Rect with rounded corners on the top only (data end), square at the baseline
function topRoundedRect(x, y, w, h, r) {
  const rr = Math.min(r, w / 2, h)
  return `M${x},${y + h}V${y + rr}Q${x},${y} ${x + rr},${y}H${x + w - rr}Q${x + w},${y} ${x + w},${y + rr}V${y + h}Z`
}
// Rect rounded on the right end only, for horizontal bars
function rightRoundedRect(x, y, w, h, r) {
  const rr = Math.min(r, h / 2, w)
  return `M${x},${y}H${x + w - rr}Q${x + w},${y} ${x + w},${y + rr}V${y + h - rr}Q${x + w},${y + h} ${x + w - rr},${y + h}H${x}Z`
}

export function Legend({ items }) {
  return (
    <div className="sa-legend">
      {items.map(it => (
        <span key={it.key} className="sa-legend-item">
          {it.dashed
            ? <span className="sa-swatch-line" />
            : <span className="sa-swatch" style={{ background: it.color }} />}
          {it.label}
        </span>
      ))}
    </div>
  )
}

// ── Monthly spend: stacked columns by category ──────────────────────────────
export function MonthlyChart({ monthly, series, colorOf, focus, selected, onSelect }) {
  const [ref, width] = useWidth()
  const [tip, setTip] = useState(null)
  const [hover, setHover] = useState(null)

  const height = 280
  const pad = { top: 26, right: 8, bottom: 30, left: 52 }
  const innerW = Math.max(width - pad.left - pad.right, 0)
  const innerH = height - pad.top - pad.bottom

  // Each month split into the visible series (top categories + Other)
  const rows = monthly.map(m => {
    const parts = series.map(s => ({
      key: s,
      value: s === 'other_group'
        ? Object.entries(m.by_category).filter(([c]) => !series.includes(c)).reduce((a, [, v]) => a + v, 0)
        : m.by_category[s] || 0,
    }))
    const shown = focus ? parts.filter(p => p.key === focus) : parts
    return { month: m.month, total: m.total, count: m.count, parts, shown, height: shown.reduce((a, p) => a + p.value, 0) }
  })

  const max = Math.max(...rows.map(r => r.height), 1)
  const ticks = niceTicks(max)
  const top = ticks[ticks.length - 1]
  const y = v => pad.top + innerH - (v / top) * innerH
  const band = rows.length ? innerW / rows.length : 0
  const barW = Math.min(Math.max(band * 0.56, 8), 64)
  const avg = rows.length ? rows.reduce((a, r) => a + r.height, 0) / rows.length : 0
  const maxIdx = rows.reduce((best, r, i) => (r.height > rows[best].height ? i : best), 0)
  const labelAll = rows.length <= 8

  function show(e, r, i) {
    const box = ref.current.getBoundingClientRect()
    setHover(i)
    const parts = r.shown.filter(p => p.value > 0).sort((a, b) => b.value - a.value)
    setTip({
      x: e.clientX - box.left,
      y: Math.max(e.clientY - box.top - 20, 0),
      content: (
        <TipRows
          title={monthLabel(r.month, true)}
          rows={parts.map(p => ({ key: p.key, color: colorOf(p.key), label: catLabel(p.key), value: money(p.value) }))}
          total={{ label: focus ? `${r.count} purchases in month` : `Total · ${r.count} purchases`, value: money(focus ? r.height : r.total) }}
        />
      ),
    })
  }

  return (
    <div ref={ref} className="sa-chart" onMouseLeave={() => { setTip(null); setHover(null) }}>
      {width > 0 && (
        <svg width={width} height={height} role="img" aria-label="Spend per month by category">
          {ticks.map(t => (
            <g key={t}>
              <line x1={pad.left} x2={width - pad.right} y1={y(t)} y2={y(t)} className={t === 0 ? 'sa-baseline' : 'sa-grid'} />
              <text x={pad.left - 8} y={y(t)} dy="0.32em" textAnchor="end" className="sa-axis">{compactMoney(t)}</text>
            </g>
          ))}

          {rows.map((r, i) => {
            const cx = pad.left + band * i + band / 2
            const x = cx - barW / 2
            let acc = 0
            const visible = r.shown.filter(p => p.value > 0)
            const isSel = selected === r.month
            return (
              <g key={r.month}>
                {(hover === i || isSel) && (
                  <rect x={pad.left + band * i + 2} y={pad.top} width={band - 4} height={innerH}
                    className={isSel ? 'sa-col-selected' : 'sa-col-hover'} rx="6" />
                )}
                {visible.map((p, j) => {
                  const h = (p.value / top) * innerH
                  const yTop = y(acc + p.value)
                  acc += p.value
                  const isTop = j === visible.length - 1
                  // 2px surface gap between stacked segments
                  const gap = j > 0 ? 2 : 0
                  const segH = Math.max(h - gap, 0.5)
                  return isTop ? (
                    <path key={p.key} d={topRoundedRect(x, yTop, barW, segH, 4)} fill={colorOf(p.key)} />
                  ) : (
                    <rect key={p.key} x={x} y={yTop} width={barW} height={segH} fill={colorOf(p.key)} />
                  )
                })}
                {(labelAll || i === maxIdx || i === rows.length - 1) && r.height > 0 && (
                  <text x={cx} y={y(r.height) - 7} textAnchor="middle" className="sa-value">{compactMoney(r.height)}</text>
                )}
                <text x={cx} y={height - 10} textAnchor="middle" className={`sa-axis${isSel ? ' sa-axis-strong' : ''}`}>
                  {rows.length > 12 && i % 2 ? '' : monthLabel(r.month)}
                </text>
                {/* hit target: the whole column */}
                <rect x={pad.left + band * i} y={pad.top} width={band} height={innerH + pad.bottom}
                  fill="transparent" style={{ cursor: 'pointer' }}
                  onMouseMove={e => show(e, r, i)} onClick={() => onSelect?.(r.month)} />
              </g>
            )
          })}

          {rows.length > 1 && (
            <g pointerEvents="none">
              <line x1={pad.left} x2={width - pad.right} y1={y(avg)} y2={y(avg)} className="sa-avg" />
            </g>
          )}
        </svg>
      )}
      <Tooltip tip={tip} width={width} />
    </div>
  )
}

// ── Month vs month: paired horizontal bars per category ─────────────────────
export function CompareChart({ a, b, colorA, colorB }) {
  const [ref, width] = useWidth()
  const [tip, setTip] = useState(null)
  const [hover, setHover] = useState(null)

  const cats = Array.from(new Set([...Object.keys(a.by_category), ...Object.keys(b.by_category)]))
    .map(c => ({ cat: c, va: a.by_category[c] || 0, vb: b.by_category[c] || 0 }))
    .sort((p, q) => Math.max(q.va, q.vb) - Math.max(p.va, p.vb))

  const labelW = Math.min(150, Math.max(width * 0.3, 96))
  const deltaW = 92
  const rowH = 34
  const barH = 10
  const pad = { top: 4, bottom: 4 }
  const height = pad.top + cats.length * rowH + pad.bottom
  const plotW = Math.max(width - labelW - deltaW - 12, 10)
  const max = Math.max(...cats.map(c => Math.max(c.va, c.vb)), 1)
  const w = v => (v / max) * plotW

  function show(e, c, i) {
    const box = ref.current.getBoundingClientRect()
    setHover(i)
    const diff = c.vb - c.va
    setTip({
      x: e.clientX - box.left,
      y: Math.max(e.clientY - box.top - 20, 0),
      content: (
        <TipRows
          title={catLabel(c.cat)}
          rows={[
            { key: 'a', color: colorA, label: monthLabel(a.month, true), value: money(c.va) },
            { key: 'b', color: colorB, label: monthLabel(b.month, true), value: money(c.vb) },
          ]}
          total={{ label: 'Change', value: `${diff >= 0 ? '+' : '−'}${money(Math.abs(diff))}` }}
        />
      ),
    })
  }

  return (
    <div ref={ref} className="sa-chart" onMouseLeave={() => { setTip(null); setHover(null) }}>
      {width > 0 && (
        <svg width={width} height={height} role="img"
          aria-label={`Spend by category, ${monthLabel(a.month, true)} compared with ${monthLabel(b.month, true)}`}>
          {cats.map((c, i) => {
            const y0 = pad.top + i * rowH
            const diff = c.vb - c.va
            const pct = c.va > 0 ? Math.round((diff / c.va) * 100) : null
            const x0 = labelW
            return (
              <g key={c.cat}>
                {hover === i && <rect x={0} y={y0} width={width} height={rowH} className="sa-col-hover" rx="6" />}
                <text x={labelW - 10} y={y0 + rowH / 2} dy="0.32em" textAnchor="end" className="sa-cat">{catLabel(c.cat)}</text>
                <line x1={x0} x2={x0} y1={y0 + 4} y2={y0 + rowH - 4} className="sa-baseline" />
                {c.va > 0 && <path d={rightRoundedRect(x0, y0 + rowH / 2 - barH - 1, w(c.va), barH, 4)} fill={colorA} />}
                {c.vb > 0 && <path d={rightRoundedRect(x0, y0 + rowH / 2 + 1, w(c.vb), barH, 4)} fill={colorB} />}
                <text x={width - 4} y={y0 + rowH / 2} dy="0.32em" textAnchor="end" className="sa-delta">
                  {diff === 0 ? '—' : `${diff > 0 ? '▲' : '▼'} ${compactMoney(Math.abs(diff))}${pct !== null && Math.abs(pct) < 1000 ? ` · ${Math.abs(pct)}%` : ''}`}
                </text>
                <rect x={0} y={y0} width={width} height={rowH} fill="transparent" onMouseMove={e => show(e, c, i)} />
              </g>
            )
          })}
        </svg>
      )}
      <Tooltip tip={tip} width={width} />
    </div>
  )
}

// ── Ranked horizontal bars (categories, merchants) ──────────────────────────
export function BarList({ items, colorOf, onPick, active, valueLabel }) {
  const [ref, width] = useWidth()
  const [tip, setTip] = useState(null)
  const [hover, setHover] = useState(null)

  const rowH = 30
  const barH = 10
  const labelW = Math.min(170, Math.max(width * 0.38, 100))
  const valueW = 74
  const plotW = Math.max(width - labelW - valueW - 8, 10)
  const max = Math.max(...items.map(i => i.total), 1)
  const height = items.length * rowH + 4
  const maxChars = Math.max(Math.floor((labelW - 12) / 6.6), 6)

  function show(e, it, i) {
    const box = ref.current.getBoundingClientRect()
    setHover(i)
    setTip({ x: e.clientX - box.left, y: Math.max(e.clientY - box.top - 20, 0), content: it.tip })
  }

  return (
    <div ref={ref} className="sa-chart" onMouseLeave={() => { setTip(null); setHover(null) }}>
      {width > 0 && (
        <svg width={width} height={height} role="img" aria-label={valueLabel}>
          {items.map((it, i) => {
            const y0 = 2 + i * rowH
            const dim = active && active !== it.key
            return (
              <g key={it.key} opacity={dim ? 0.35 : 1}>
                {hover === i && <rect x={0} y={y0} width={width} height={rowH} className="sa-col-hover" rx="6" />}
                <text x={labelW - 10} y={y0 + rowH / 2} dy="0.32em" textAnchor="end" className="sa-cat">
                  {it.label.length > maxChars ? `${it.label.slice(0, maxChars - 1)}…` : it.label}
                </text>
                <path d={rightRoundedRect(labelW, y0 + (rowH - barH) / 2, Math.max((it.total / max) * plotW, 2), barH, 4)}
                  fill={colorOf(it.colorKey)} />
                <text x={width - 4} y={y0 + rowH / 2} dy="0.32em" textAnchor="end" className="sa-value">{it.value}</text>
                <rect x={0} y={y0} width={width} height={rowH} fill="transparent"
                  style={{ cursor: onPick ? 'pointer' : 'default' }}
                  onMouseMove={e => show(e, it, i)} onClick={() => onPick?.(it.key)} />
              </g>
            )
          })}
        </svg>
      )}
      <Tooltip tip={tip} width={width} />
    </div>
  )
}

export { TipRows }

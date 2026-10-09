import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { getSpendSummary } from '../api.js'
import {
  BarList, CompareChart, Legend, MonthlyChart, TipRows,
  catLabel, compactMoney, money, monthLabel,
} from '../components/SpendCharts.jsx'

// Validated categorical palette (dark steps, checked against --navy-900).
// Top five categories get a slot in this fixed order; the rest fold into Other.
const SLOTS = ['var(--sa-s1)', 'var(--sa-s2)', 'var(--sa-s3)', 'var(--sa-s4)', 'var(--sa-s5)']
const OTHER = 'var(--sa-other)'

const css = `
.sa-root {
  --sa-s1: #3987e5; --sa-s2: #d95926; --sa-s3: #199e70; --sa-s4: #c98500; --sa-s5: #d55181;
  --sa-other: #64748b;
  --sa-grid: rgba(148,163,184,0.12);
  --sa-axis: #94a3b8;
}
.sa-page { max-width: 1040px; margin: 0 auto; padding: 32px 24px 80px; }
.sa-header { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 28px; flex-wrap: wrap; }
.sa-logo { font-size: 13px; font-weight: 600; letter-spacing: 0.12em; text-transform: uppercase; color: var(--amber-400); }
.sa-btn {
  background: var(--navy-800); border: 1px solid var(--navy-600); border-radius: var(--radius-md);
  color: var(--slate-300); font-family: var(--font-sans); font-size: 13px; padding: 9px 18px; cursor: pointer;
  transition: all var(--transition);
}
.sa-btn:hover { border-color: var(--amber-500); color: var(--amber-400); }
.sa-title { font-family: var(--font-display); font-size: clamp(28px, 5vw, 40px); line-height: 1.15; margin-bottom: 6px; }
.sa-sub { color: var(--slate-400); font-size: 14px; margin-bottom: 20px; }

.sa-filters { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 24px; }
.sa-pill {
  padding: 7px 14px; border-radius: 20px; border: 1px solid var(--navy-600); background: var(--navy-800);
  color: var(--slate-400); font-size: 12px; font-weight: 500; cursor: pointer; font-family: var(--font-sans);
  transition: all var(--transition);
}
.sa-pill:hover { color: var(--white); border-color: var(--navy-500); }
.sa-pill.active { border-color: var(--amber-500); color: var(--amber-400); background: rgba(245,158,11,0.06); }

.sa-kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 20px; }
.sa-kpi { background: var(--navy-900); border: 1px solid var(--navy-700); border-radius: var(--radius-lg); padding: 16px 18px; }
.sa-kpi-label { font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--slate-400); }
.sa-kpi-value { font-family: var(--font-mono); font-size: 24px; font-weight: 500; letter-spacing: -0.02em; margin-top: 4px; }
.sa-kpi-value.txt { font-family: var(--font-sans); font-weight: 600; font-size: 21px; letter-spacing: 0; }
.sa-kpi-note { font-size: 12px; color: var(--slate-400); margin-top: 2px; }

.sa-section { background: var(--navy-900); border: 1px solid var(--navy-700); border-radius: var(--radius-xl); padding: 24px; margin-bottom: 20px; animation: fadeUp 350ms ease both; }
.sa-section-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; flex-wrap: wrap; margin-bottom: 14px; }
.sa-h { font-size: 17px; font-weight: 600; }
.sa-hint { font-size: 12px; color: var(--slate-400); margin-top: 2px; }
.sa-grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); gap: 20px; }
.sa-grid2 > .sa-section { margin-bottom: 0; }
.sa-link { background: none; border: none; color: var(--amber-400); font-size: 12px; cursor: pointer; font-family: var(--font-sans); padding: 0; }
.sa-link:hover { text-decoration: underline; }

.sa-select {
  background: var(--navy-800); color: var(--white); border: 1px solid var(--navy-600); border-radius: var(--radius-sm);
  padding: 6px 10px; font-family: var(--font-sans); font-size: 13px;
}
.sa-compare-controls { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.sa-compare-summary { font-size: 14px; color: var(--slate-300); margin: 4px 0 14px; }
.sa-compare-summary strong { color: var(--white); font-family: var(--font-mono); font-weight: 500; }

.sa-chart { position: relative; width: 100%; }
.sa-chart svg { display: block; overflow: visible; }
.sa-grid { stroke: var(--sa-grid); stroke-width: 1; }
.sa-baseline { stroke: var(--navy-500); stroke-width: 1; }
.sa-avg { stroke: var(--slate-400); stroke-width: 1; stroke-dasharray: 4 4; opacity: 0.7; }
.sa-axis { fill: var(--sa-axis); font-size: 11px; font-family: var(--font-sans); }
.sa-axis-strong { fill: var(--amber-400); font-weight: 600; }
.sa-value { fill: var(--slate-200); font-size: 11px; font-family: var(--font-mono); }
.sa-cat { fill: var(--slate-300); font-size: 12px; font-family: var(--font-sans); }
.sa-delta { fill: var(--slate-300); font-size: 11px; font-family: var(--font-mono); }
.sa-col-hover { fill: rgba(148,163,184,0.07); }
.sa-col-selected { fill: rgba(245,158,11,0.08); stroke: rgba(245,158,11,0.35); stroke-width: 1; }

.sa-legend { display: flex; flex-wrap: wrap; gap: 6px 14px; font-size: 12px; color: var(--slate-300); margin-bottom: 10px; }
.sa-legend-item { display: inline-flex; align-items: center; gap: 6px; }
.sa-swatch-line { width: 14px; border-top: 1px dashed var(--slate-400); display: inline-block; }
.sa-swatch { width: 10px; height: 10px; border-radius: 3px; display: inline-block; flex-shrink: 0; }

.sa-tip {
  position: absolute; pointer-events: none; z-index: 5; min-width: 190px; max-width: 240px;
  background: var(--navy-800); border: 1px solid var(--navy-600); border-radius: var(--radius-md);
  padding: 10px 12px; font-size: 12px; box-shadow: 0 8px 24px rgba(0,0,0,0.4);
}
.sa-tip-title { font-weight: 600; color: var(--white); margin-bottom: 6px; }
.sa-tip-row { display: flex; align-items: center; gap: 8px; color: var(--slate-300); line-height: 1.7; }
.sa-tip-label { flex: 1; }
.sa-tip-value { font-family: var(--font-mono); color: var(--white); }
.sa-tip-total { border-top: 1px solid var(--navy-600); margin-top: 6px; padding-top: 6px; }

.sa-table-wrap { overflow-x: auto; margin-top: 12px; }
.sa-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.sa-table th, .sa-table td { padding: 7px 10px; text-align: right; border-bottom: 1px solid var(--navy-700); white-space: nowrap; }
.sa-table th { color: var(--slate-400); font-weight: 500; }
.sa-table th:first-child, .sa-table td:first-child { text-align: left; }
.sa-table td { font-family: var(--font-mono); color: var(--slate-200); }
.sa-table td.txt { font-family: var(--font-sans); }

.sa-empty { text-align: center; color: var(--slate-400); padding: 60px 0; }
.sa-note { font-size: 13px; color: var(--slate-400); padding: 12px 0; }
@media (max-width: 520px) {
  .sa-page { padding: 24px 16px 60px; }
  .sa-grid2 { grid-template-columns: 1fr; }
  .sa-section { padding: 18px 14px; }
}
`

function pctChange(a, b) {
  if (!a) return null
  return Math.round(((b - a) / a) * 100)
}

export default function SpendAnalyserPage() {
  const { sessionId } = useParams()
  const navigate = useNavigate()

  const [cardId, setCardId] = useState(null)
  const [data, setData] = useState(null)
  const [overall, setOverall] = useState(null) // all-cards summary, fixes category colours
  const [error, setError] = useState('')
  const [focus, setFocus] = useState(null)
  const [monthA, setMonthA] = useState(null)
  const [monthB, setMonthB] = useState(null)
  const [showTable, setShowTable] = useState(false)

  useEffect(() => {
    let live = true
    getSpendSummary(sessionId, cardId)
      .then(d => {
        if (!live) return
        setData(d)
        if (!cardId) setOverall(d)
        const ms = d.monthly.map(m => m.month)
        setMonthB(b => (ms.includes(b) ? b : ms[ms.length - 1] ?? null))
        setMonthA(a => (ms.includes(a) ? a : ms[ms.length - 2] ?? null))
      })
      .catch(e => live && setError(e.status === 404 ? 'This session has expired or does not exist.' : 'Could not load your spending.'))
    return () => { live = false }
  }, [sessionId, cardId])

  // Colour follows the category, decided once from the all-cards view
  const { series, colorOf } = useMemo(() => {
    const top = (overall?.categories || []).slice(0, SLOTS.length).map(c => c.category)
    const hasOther = (overall?.categories || []).length > top.length
    const color = key => {
      const i = top.indexOf(key)
      return i >= 0 ? SLOTS[i] : OTHER
    }
    return { series: hasOther ? [...top, 'other_group'] : top, colorOf: color }
  }, [overall])

  if (error) return <Shell navigate={navigate} sessionId={sessionId}><div className="sa-empty">{error}</div></Shell>
  if (!data) return <Shell navigate={navigate} sessionId={sessionId}><div className="sa-empty">Loading your spending…</div></Shell>

  const months = data.monthly
  const byMonth = Object.fromEntries(months.map(m => [m.month, m]))
  const avg = months.length ? data.total_spend / months.length : 0
  const last = months[months.length - 1]
  const prev = months[months.length - 2]
  const lastChange = last && prev ? pctChange(prev.total, last.total) : null
  const topCat = data.categories[0]
  const a = byMonth[monthA]
  const b = byMonth[monthB]

  function selectMonth(m) {
    const i = months.findIndex(x => x.month === m)
    setMonthB(m)
    if (i > 0) setMonthA(months[i - 1].month)
    else if (months.length > 1) setMonthA(months[1].month)
  }

  const legendItems = series.map(s => ({ key: s, label: catLabel(s), color: s === 'other_group' ? OTHER : colorOf(s) }))
  const tableCats = series.filter(s => s !== 'other_group')

  return (
    <Shell navigate={navigate} sessionId={sessionId}>
      <h1 className="sa-title">Spend Analyser</h1>
      <p className="sa-sub">
        {data.transactions} purchases across {months.length} month{months.length === 1 ? '' : 's'}
        {data.refunds > 0 && ` · ${money(data.refunds)} refunded`}
      </p>

      {data.cards.length > 1 && (
        <div className="sa-filters" role="group" aria-label="Filter by card">
          <button className={`sa-pill${!cardId ? ' active' : ''}`} onClick={() => setCardId(null)}>All cards</button>
          {data.cards.map(c => (
            <button key={c.card_id} className={`sa-pill${cardId === c.card_id ? ' active' : ''}`} onClick={() => setCardId(c.card_id)}>
              {c.card_name}
            </button>
          ))}
        </div>
      )}

      {months.length === 0 ? (
        <div className="sa-section"><div className="sa-empty">No purchases were found in these statements.</div></div>
      ) : (
        <>
          <div className="sa-kpis">
            <Kpi label="Total spend" value={money(data.total_spend)} note={`${monthLabel(months[0].month, true)} to ${monthLabel(last.month, true)}`} />
            <Kpi label="Average per month" value={money(avg)} note={`over ${months.length} month${months.length === 1 ? '' : 's'}`} />
            <Kpi
              label={`${monthLabel(last.month, true)} vs previous`}
              value={lastChange === null ? '—' : `${lastChange > 0 ? '▲' : lastChange < 0 ? '▼' : ''} ${Math.abs(lastChange)}%`}
              note={prev ? `${money(last.total)} vs ${money(prev.total)}` : 'needs two months'}
            />
            {topCat && <Kpi text label="Biggest category" value={catLabel(topCat.category)} note={`${money(topCat.total)} · ${Math.round(topCat.share * 100)}% of spend`} />}
          </div>

          <section className="sa-section">
            <div className="sa-section-head">
              <div>
                <div className="sa-h">Monthly spend{focus ? ` · ${catLabel(focus)}` : ''}</div>
                <div className="sa-hint">Hover a month for the breakdown. Click one to compare it with the month before.</div>
              </div>
              <div style={{ display: 'flex', gap: 14 }}>
                {focus && <button className="sa-link" onClick={() => setFocus(null)}>Show all categories</button>}
                <button className="sa-link" onClick={() => setShowTable(t => !t)}>{showTable ? 'Hide table' : 'Show table'}</button>
              </div>
            </div>
            <Legend items={[
              ...(focus ? legendItems.filter(l => l.key === focus) : legendItems),
              ...(months.length > 1 ? [{ key: 'avg', label: `Monthly average ${compactMoney(avg)}`, dashed: true }] : []),
            ]} />
            <MonthlyChart monthly={months} series={series} colorOf={k => (k === 'other_group' ? OTHER : colorOf(k))}
              focus={focus} selected={months.length > 1 ? monthB : null} onSelect={selectMonth} />
            {showTable && (
              <div className="sa-table-wrap">
                <table className="sa-table">
                  <thead>
                    <tr><th>Month</th>{tableCats.map(c => <th key={c}>{catLabel(c)}</th>)}{series.includes('other_group') && <th>Other</th>}<th>Total</th></tr>
                  </thead>
                  <tbody>
                    {months.map(m => {
                      const other = Object.entries(m.by_category).filter(([c]) => !tableCats.includes(c)).reduce((s, [, v]) => s + v, 0)
                      return (
                        <tr key={m.month}>
                          <td className="txt">{monthLabel(m.month, true)}</td>
                          {tableCats.map(c => <td key={c}>{money(m.by_category[c] || 0)}</td>)}
                          {series.includes('other_group') && <td>{money(other)}</td>}
                          <td>{money(m.total)}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="sa-section">
            <div className="sa-section-head">
              <div>
                <div className="sa-h">Compare months</div>
                <div className="sa-hint">Spend per category in two months, side by side.</div>
              </div>
              {months.length > 1 && (
                <div className="sa-compare-controls">
                  <MonthSelect value={monthA} months={months} onChange={setMonthA} label="First month" />
                  <span style={{ color: 'var(--slate-400)', fontSize: 13 }}>vs</span>
                  <MonthSelect value={monthB} months={months} onChange={setMonthB} label="Second month" />
                </div>
              )}
            </div>
            {months.length < 2 || !a || !b ? (
              <div className="sa-note">Upload statements for two or more months to compare them.</div>
            ) : (
              <>
                <p className="sa-compare-summary">
                  You spent <strong>{money(b.total)}</strong> in {monthLabel(b.month, true)}
                  {a.month === b.month ? '.' : (
                    <>, {b.total >= a.total ? 'up' : 'down'} <strong>{money(Math.abs(b.total - a.total))}</strong>
                      {pctChange(a.total, b.total) !== null && ` (${Math.abs(pctChange(a.total, b.total))}%)`} from {monthLabel(a.month, true)}.</>
                  )}
                </p>
                <Legend items={[
                  { key: 'a', label: monthLabel(a.month, true), color: 'var(--sa-s1)' },
                  { key: 'b', label: monthLabel(b.month, true), color: 'var(--sa-s2)' },
                ]} />
                <CompareChart a={a} b={b} colorA="var(--sa-s1)" colorB="var(--sa-s2)" />
              </>
            )}
          </section>

          <div className="sa-grid2">
            <section className="sa-section">
              <div className="sa-section-head">
                <div>
                  <div className="sa-h">Where it goes</div>
                  <div className="sa-hint">Click a category to see it month by month.</div>
                </div>
              </div>
              <BarList
                valueLabel="Spend by category"
                active={focus}
                onPick={k => setFocus(f => (f === k ? null : k))}
                colorOf={k => colorOf(k)}
                items={data.categories.map(c => ({
                  key: c.category, colorKey: c.category, label: catLabel(c.category), total: c.total,
                  value: compactMoney(c.total),
                  tip: <TipRows title={catLabel(c.category)} rows={[
                    { key: 't', label: 'Spend', value: money(c.total) },
                    { key: 's', label: 'Share', value: `${(c.share * 100).toFixed(1)}%` },
                    { key: 'n', label: 'Purchases', value: c.count },
                  ]} />,
                }))}
              />
            </section>

            <section className="sa-section">
              <div className="sa-section-head">
                <div>
                  <div className="sa-h">Top merchants</div>
                  <div className="sa-hint">Coloured by category.</div>
                </div>
              </div>
              <BarList
                valueLabel="Spend by merchant"
                colorOf={k => colorOf(k)}
                items={data.merchants.map(m => ({
                  key: m.merchant, colorKey: m.category, label: m.merchant, total: m.total,
                  value: compactMoney(m.total),
                  tip: <TipRows title={m.merchant} rows={[
                    { key: 't', label: 'Spend', value: money(m.total) },
                    { key: 'n', label: 'Purchases', value: m.count },
                    { key: 'c', label: 'Category', value: catLabel(m.category) },
                  ]} />,
                }))}
              />
            </section>
          </div>

          {data.largest.length > 0 && (
            <section className="sa-section" style={{ marginTop: 20 }}>
              <div className="sa-section-head"><div className="sa-h">Largest purchases</div></div>
              <div className="sa-table-wrap">
                <table className="sa-table">
                  <thead><tr><th>Date</th><th style={{ textAlign: 'left' }}>Merchant</th><th style={{ textAlign: 'left' }}>Category</th>{data.cards.length > 1 && <th style={{ textAlign: 'left' }}>Card</th>}<th>Amount</th></tr></thead>
                  <tbody>
                    {data.largest.map((t, i) => (
                      <tr key={i}>
                        <td className="txt">{t.date}</td>
                        <td className="txt" style={{ textAlign: 'left' }}>{t.merchant}</td>
                        <td className="txt" style={{ textAlign: 'left' }}>
                          <span className="sa-swatch" style={{ background: colorOf(t.category), marginRight: 6 }} />{catLabel(t.category)}
                        </td>
                        {data.cards.length > 1 && <td className="txt" style={{ textAlign: 'left' }}>{t.card_name}</td>}
                        <td>{money(t.amount)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </>
      )}
    </Shell>
  )
}

function Shell({ children, navigate, sessionId }) {
  return (
    <div className="sa-root">
      <style>{css}</style>
      <div className="sa-page">
        <div className="sa-header">
          <div className="sa-logo">💳 CardSense AI</div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="sa-btn" onClick={() => navigate(`/results/${sessionId}`)}>← Results</button>
            <button className="sa-btn" onClick={() => navigate('/')}>New analysis</button>
          </div>
        </div>
        {children}
      </div>
    </div>
  )
}

function Kpi({ label, value, note, text }) {
  return (
    <div className="sa-kpi">
      <div className="sa-kpi-label">{label}</div>
      <div className={`sa-kpi-value${text ? ' txt' : ''}`}>{value}</div>
      {note && <div className="sa-kpi-note">{note}</div>}
    </div>
  )
}

function MonthSelect({ value, months, onChange, label }) {
  return (
    <select className="sa-select" aria-label={label} value={value || ''} onChange={e => onChange(e.target.value)}>
      {months.map(m => <option key={m.month} value={m.month}>{monthLabel(m.month, true)}</option>)}
    </select>
  )
}

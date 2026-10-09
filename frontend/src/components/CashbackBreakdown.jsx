import { money, catLabel, monthLabel } from '../format.js'

const styles = `
.breakdown-wrap { display: flex; flex-direction: column; gap: 24px; }
.breakdown-scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; }
.breakdown-table { width: 100%; border-collapse: collapse; }
.breakdown-table th {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--slate-400);
  text-align: left;
  padding: 0 12px 10px;
  border-bottom: 1px solid var(--navy-700);
}
.breakdown-table th:not(:first-child) { text-align: right; }
.breakdown-table td {
  padding: 10px 12px;
  font-size: 13px;
  border-bottom: 1px solid rgba(var(--tint), 0.04);
}
.bd-row { animation: fadeUp 200ms ease both; }
.bd-row.earned { background: rgba(34,197,94,0.03); }
.bd-row.partial { background: rgba(249,115,22,0.04); }
.bd-row.missed  { background: rgba(239,68,68,0.04); }
.bd-row.total {
  border-top: 1px solid var(--navy-600);
  background: rgba(var(--tint), 0.03);
}
.bd-row.total td { font-weight: 600; font-family: var(--font-mono); padding-top: 14px; }
.bd-cat {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--white);
}
.bd-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dot-green  { background: var(--green-500); }
.dot-orange { background: var(--orange-500); }
.dot-red    { background: var(--red-500); }
.dot-grey   { background: var(--slate-400); }
.bd-num { font-family: var(--font-mono); text-align: right; }
.bd-earned { color: var(--green-400); }
.bd-missed { color: var(--red-400); }
.bd-rate { color: var(--slate-400); font-size: 12px; }
.util-bar-wrap {
  display: flex;
  align-items: center;
  gap: 6px;
  justify-content: flex-end;
}
.util-bar-bg {
  width: 60px;
  height: 4px;
  background: rgba(var(--tint), 0.08);
  border-radius: 2px;
  overflow: hidden;
}
.util-bar-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 600ms ease;
}
.util-pct { font-family: var(--font-mono); font-size: 12px; min-width: 32px; text-align: right; }
.summary-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: var(--navy-800);
  border: 1px solid var(--navy-600);
  border-radius: var(--radius-md);
  padding: 16px 20px;
}
.summary-item { text-align: center; }
.summary-label { font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--slate-400); margin-bottom: 4px; }
.summary-val { font-family: var(--font-mono); font-size: 20px; font-weight: 500; }
.val-green { color: var(--green-400); }
.val-red   { color: var(--red-400); }
.summary-divider { width: 1px; height: 40px; background: var(--navy-600); }

/* Phones: each category becomes a two-line row instead of a cut-off table */
@media (max-width: 560px) {
  .summary-row { display: grid; grid-template-columns: 1fr 1fr; gap: 14px 8px; padding: 14px; }
  .summary-divider { display: none; }
  .summary-val { font-size: 18px; }
  .breakdown-table thead { display: none; }
  .breakdown-table tr { display: grid; grid-template-columns: auto auto 1fr; align-items: center; column-gap: 14px; padding: 10px 10px; border-bottom: 1px solid rgba(var(--tint), 0.04); }
  .breakdown-table td { padding: 0; border: none; }
  .breakdown-table td:first-child { grid-column: 1 / -1; margin-bottom: 6px; }
  .breakdown-table td[data-label]::before {
    content: attr(data-label) ' '; font-family: var(--font-sans); font-size: 10px; letter-spacing: 0.06em;
    text-transform: uppercase; color: var(--slate-400); margin-right: 4px;
  }
  .bd-row.total .bd-util { visibility: hidden; }
  .util-bar-bg { width: 48px; }
}

/* SVG bar chart */
.trend-chart { width: 100%; max-width: 560px; max-height: 220px; display: block; margin: 0 auto; overflow: hidden; }
.trend-title {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--slate-400);
  margin-bottom: 10px;
}
`

export default function CashbackBreakdown({ cashbackResult, multiMonth }) {
  if (!cashbackResult) return null

  const { earned_breakdown, missed_breakdown, utilization_score, monthly_breakdown, trend } = cashbackResult

  // Merge all categories
  const allCats = new Set([...Object.keys(earned_breakdown), ...Object.keys(missed_breakdown)])
  const rows = Array.from(allCats).map(cat => {
    const earned = earned_breakdown[cat] || 0
    const missed = missed_breakdown[cat] || 0
    const total = earned + missed
    const pct = total > 0 ? Math.round((earned / total) * 100) : (earned > 0 ? 100 : 0)
    return { cat, earned, missed, total, pct }
  }).sort((a, b) => b.total - a.total)

  const totalEarned = Object.values(earned_breakdown).reduce((s, v) => s + v, 0)
  const totalMissed = Object.values(missed_breakdown).reduce((s, v) => s + v, 0)

  // SVG bar chart for multi-month
  const chartData = monthly_breakdown || []
  const maxEarned = Math.max(...chartData.map(m => m.earned), 1)
  const chartH = 100
  const chartW = 300
  const barW = chartData.length > 0 ? Math.min(40, (chartW - 20) / chartData.length - 8) : 30

  function rowClass(pct) {
    if (pct >= 80) return 'earned'
    if (pct >= 30) return 'partial'
    if (pct > 0) return 'missed'
    return 'missed'
  }

  function dotClass(pct) {
    if (pct >= 80) return 'dot-green'
    if (pct >= 30) return 'dot-orange'
    return 'dot-red'
  }

  return (
    <>
      <style>{styles}</style>
      <div className="breakdown-wrap">
        {/* Summary bar */}
        <div className="summary-row">
          <div className="summary-item">
            <div className="summary-label">Earned</div>
            <div className="summary-val val-green">{money(totalEarned)}</div>
          </div>
          <div className="summary-divider" />
          <div className="summary-item">
            <div className="summary-label">Missed</div>
            <div className="summary-val val-red">{money(totalMissed)}</div>
          </div>
          <div className="summary-divider" />
          <div className="summary-item">
            <div className="summary-label">Utilization</div>
            <div className="summary-val" style={{ color: utilization_score >= 70 ? 'var(--green-400)' : utilization_score >= 40 ? 'var(--orange-400)' : 'var(--red-400)' }}>
              {utilization_score}%
            </div>
          </div>
          <div className="summary-divider" />
          <div className="summary-item">
            <div className="summary-label">Trend</div>
            <div className="summary-val" style={{ fontSize: 14, color: trend === 'improving' ? 'var(--green-400)' : trend === 'declining' ? 'var(--red-400)' : 'var(--slate-400)' }}>
              {trend === 'improving' ? '↑ Up' : trend === 'declining' ? '↓ Down' : '→ Flat'}
            </div>
          </div>
        </div>

        {/* Multi-month bar chart */}
        {chartData.length > 1 && (
          <div>
            <div className="trend-title">Monthly cashback trend</div>
            <svg className="trend-chart" viewBox={`0 0 ${chartW} ${chartH + 24}`} xmlns="http://www.w3.org/2000/svg">
              {chartData.map((m, i) => {
                const x = 10 + i * ((chartW - 20) / chartData.length) + (((chartW - 20) / chartData.length) - barW) / 2
                const barHeight = (m.earned / maxEarned) * chartH
                const y = chartH - barHeight
                return (
                  <g key={m.month}>
                    <rect
                      x={x} y={y}
                      width={barW} height={barHeight}
                      fill="rgba(245,158,11,0.7)"
                      rx="3"
                    />
                    <text x={x + barW / 2} y={chartH + 14} textAnchor="middle" fontSize="9" fill="var(--slate-400)">
                      {monthLabel(m.month)}
                    </text>
                    {barHeight > 16 && (
                      <text x={x + barW / 2} y={y + 12} textAnchor="middle" fontSize="8" fill="rgba(var(--tint), 0.8)">
                        {money(m.earned)}
                      </text>
                    )}
                  </g>
                )
              })}
            </svg>
          </div>
        )}

        {/* Category table */}
        <div className="breakdown-scroll">
        <table className="breakdown-table">
          <thead>
            <tr>
              <th>Category</th>
              <th>Earned</th>
              <th>Missed</th>
              <th>Utilization</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={row.cat} className={`bd-row ${rowClass(row.pct)}`} style={{ animationDelay: `${i * 40}ms` }}>
                <td>
                  <div className="bd-cat">
                    <span className="bd-dot" style={{ background: row.pct >= 80 ? 'var(--green-500)' : row.pct >= 30 ? 'var(--orange-500)' : 'var(--red-500)' }} />
                    <span>{catLabel(row.cat)}</span>
                  </div>
                </td>
                <td className="bd-num bd-earned" data-label="Earned">{money(row.earned)}</td>
                <td className="bd-num bd-missed" data-label="Missed">{row.missed > 0 ? money(row.missed) : '—'}</td>
                <td className="bd-util">
                  <div className="util-bar-wrap">
                    <div className="util-bar-bg">
                      <div
                        className="util-bar-fill"
                        style={{
                          width: `${row.pct}%`,
                          background: row.pct >= 80 ? 'var(--green-500)' : row.pct >= 30 ? 'var(--orange-500)' : 'var(--red-500)',
                        }}
                      />
                    </div>
                    <span className="util-pct" style={{ color: row.pct >= 80 ? 'var(--green-400)' : row.pct >= 30 ? 'var(--orange-400)' : 'var(--red-400)' }}>
                      {row.pct}%
                    </span>
                  </div>
                </td>
              </tr>
            ))}
            <tr className="bd-row total">
              <td style={{ color: 'var(--white)' }}>Total</td>
              <td className="bd-num bd-earned" data-label="Earned">{money(totalEarned)}</td>
              <td className="bd-num bd-missed" data-label="Missed">{money(totalMissed)}</td>
              <td className="bd-num bd-util" style={{ textAlign: 'right', color: 'var(--slate-400)' }}>—</td>
            </tr>
          </tbody>
        </table>
        </div>

        <p style={{ fontSize: 13, color: 'var(--slate-400)', textAlign: 'center' }}>
          You earned <strong style={{ color: 'var(--green-400)', fontFamily: 'var(--font-mono)' }}>{money(totalEarned)}</strong> out of a possible{' '}
          <strong style={{ color: 'var(--white)', fontFamily: 'var(--font-mono)' }}>{money(totalEarned + totalMissed)}</strong> this period.
        </p>
      </div>
    </>
  )
}

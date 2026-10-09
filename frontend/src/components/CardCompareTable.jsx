/**
 * CardCompareTable.jsx — your card next to the top alternatives, all priced
 * on the same monthly spending, category by category.
 */
import { catLabel, money } from '../format.js'

const MAX_ROWS = 6

const css = `
.cmp-scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; margin: 0 -4px; padding: 0 4px; }
.cmp-table { width: 100%; border-collapse: separate; border-spacing: 0; min-width: 560px; font-size: 13px; }
.cmp-table th, .cmp-table td { padding: 10px 12px; text-align: right; border-bottom: 1px solid var(--navy-700); }
.cmp-table th:first-child, .cmp-table td:first-child {
  text-align: left; position: sticky; left: 0; z-index: 1; background: var(--navy-900); min-width: 130px;
}
.cmp-table thead th { vertical-align: bottom; border-bottom: 1px solid var(--navy-600); }
.cmp-card-name { font-size: 13px; font-weight: 600; color: var(--white); line-height: 1.3; }
.cmp-card-bank { font-size: 11px; font-weight: 400; color: var(--slate-400); margin-top: 2px; }
.cmp-tag {
  display: inline-block; font-size: 10px; font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase;
  border-radius: 10px; padding: 2px 8px; margin-bottom: 6px;
}
.cmp-tag.current { background: rgba(148,163,184,0.12); color: var(--slate-300); }
.cmp-tag.best { background: rgba(34,197,94,0.12); color: var(--green-400); }
.cmp-col-current { background: rgba(255,255,255,0.025); }
.cmp-cat { color: var(--slate-200); }
.cmp-spend { display: block; font-size: 11px; color: var(--slate-400); font-family: var(--font-mono); margin-top: 1px; }
.cmp-num { font-family: var(--font-mono); color: var(--slate-300); white-space: nowrap; }
.cmp-num.top { color: var(--green-400); font-weight: 500; }
.cmp-num.zero { color: var(--slate-400); }
.cmp-total td { font-weight: 600; color: var(--white); border-top: 1px solid var(--navy-600); }
.cmp-total .cmp-num, .cmp-net .cmp-num { font-size: 14px; color: var(--white); }
.cmp-total .cmp-num.top, .cmp-net .cmp-num.top { color: var(--green-400); }
.cmp-net td { border-bottom: none; font-weight: 600; }
.cmp-note { font-size: 12px; color: var(--slate-400); margin-top: 12px; line-height: 1.5; }
.cmp-swipe { display: none; font-size: 11px; color: var(--slate-400); margin-bottom: 8px; }
@media (max-width: 640px) {
  .cmp-swipe { display: block; }
  .cmp-table { min-width: 520px; font-size: 12px; }
  .cmp-table th, .cmp-table td { padding: 9px 8px; }
  .cmp-table th:first-child, .cmp-table td:first-child { min-width: 108px; }
}
`

export default function CardCompareTable({ comparison }) {
  if (!comparison || !comparison.cards?.length || comparison.cards.length < 2) return null
  const { cards, categories } = comparison

  const top = categories.slice(0, MAX_ROWS)
  const rest = categories.slice(MAX_ROWS)
  const restSpend = rest.reduce((s, r) => s + r.monthly_spend, 0)
  const restOf = c => rest.reduce((s, r) => s + (c.by_category[r.category] || 0), 0)

  const rows = [
    ...top.map(r => ({ key: r.category, label: catLabel(r.category), spend: r.monthly_spend, value: c => c.by_category[r.category] || 0 })),
    ...(rest.length ? [{ key: 'rest', label: 'Everything else', spend: restSpend, value: restOf }] : []),
  ]
  const bestNet = Math.max(...cards.map(c => c.net_annual))
  const maxOf = fn => Math.max(...cards.map(fn))

  function cell(v, max, key) {
    const cls = v <= 0 ? ' zero' : v === max && max > 0 ? ' top' : ''
    return <span className={`cmp-num${cls}`} key={key}>{v > 0 ? money(v) : '—'}</span>
  }

  return (
    <div>
      <style>{css}</style>
      <div className="cmp-swipe">Swipe sideways to see every card.</div>
      <div className="cmp-scroll">
        <table className="cmp-table">
          <thead>
            <tr>
              <th scope="col"><span className="cmp-card-bank">Cashback per month</span></th>
              {cards.map(c => (
                <th scope="col" key={c.card_id} className={c.is_current ? 'cmp-col-current' : ''}>
                  {c.is_current && <span className="cmp-tag current">Your card</span>}
                  {!c.is_current && c.net_annual === bestNet && <span className="cmp-tag best">Best value</span>}
                  <div className="cmp-card-name">{c.card_name}</div>
                  {c.bank && <div className="cmp-card-bank">{c.bank}</div>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(r => {
              const max = maxOf(r.value)
              return (
                <tr key={r.key}>
                  <th scope="row" className="cmp-cat">
                    {r.label}
                    <span className="cmp-spend">{money(r.spend)} spent</span>
                  </th>
                  {cards.map(c => <td key={c.card_id} className={c.is_current ? 'cmp-col-current' : ''}>{cell(r.value(c), max)}</td>)}
                </tr>
              )
            })}
            <tr className="cmp-total">
              <th scope="row">Total per month</th>
              {cards.map(c => (
                <td key={c.card_id} className={c.is_current ? 'cmp-col-current' : ''}>{cell(c.monthly_cashback, maxOf(x => x.monthly_cashback))}</td>
              ))}
            </tr>
            <tr>
              <th scope="row" className="cmp-cat">Annual fee</th>
              {cards.map(c => (
                <td key={c.card_id} className={c.is_current ? 'cmp-col-current' : ''}>
                  <span className="cmp-num">{c.annual_fee > 0 ? `−${money(c.annual_fee)}` : 'Free'}</span>
                </td>
              ))}
            </tr>
            <tr className="cmp-net">
              <th scope="row">Net per year</th>
              {cards.map(c => (
                <td key={c.card_id} className={c.is_current ? 'cmp-col-current' : ''}>
                  <span className={`cmp-num${c.net_annual === bestNet ? ' top' : ''}`}>{money(c.net_annual)}</span>
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
      <p className="cmp-note">
        Every card is priced on the same spending: your average month from the statements. Your card shows what you
        earn today; the others assume you use their offers fully. Fees are shown before any spend-based waiver.
      </p>
    </div>
  )
}

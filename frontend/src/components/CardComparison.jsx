import { useState } from 'react'
import { InfoIcon, ArrowRightIcon } from './Icons.jsx'
import { money, catLabel } from '../format.js'

const styles = `
.comparison-wrap { display: flex; flex-direction: column; gap: 20px; }
.rec-card {
  background: var(--navy-800);
  border: 1px solid var(--navy-600);
  border-radius: var(--radius-lg);
  padding: 24px;
  animation: fadeUp 250ms ease both;
  transition: border-color var(--transition);
}
.rec-card:hover { border-color: var(--amber-500); }
.rec-rank {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--amber-400);
  margin-bottom: 8px;
}
.rec-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
  gap: 12px;
}
.rec-info {}
.rec-name {
  font-size: 17px;
  font-weight: 600;
  color: var(--white);
  margin-bottom: 3px;
}
.rec-bank { font-size: 12px; color: var(--slate-400); }
.rec-improvement {
  text-align: right;
  flex-shrink: 0;
}
.improvement-val {
  font-family: var(--font-mono);
  font-size: 20px;
  font-weight: 500;
  color: var(--green-400);
}
.improvement-label { font-size: 10px; color: var(--slate-400); letter-spacing: 0.06em; text-transform: uppercase; }
.rec-why {
  font-size: 13px;
  color: var(--slate-300);
  line-height: 1.55;
  margin-bottom: 12px;
  padding: 12px 14px;
  background: rgba(255,255,255,0.03);
  border-left: 3px solid var(--amber-500);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
}
.rec-cats {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 12px;
}
.rec-cat-tag {
  background: rgba(96,165,250,0.1);
  border: 1px solid rgba(96,165,250,0.2);
  color: var(--blue-400);
  border-radius: 20px;
  font-size: 11px;
  padding: 3px 10px;
}
.rec-caveat {
  font-size: 11px;
  color: var(--slate-400);
  display: flex;
  align-items: center;
  gap: 6px;
}
.rec-cashback-row {
  display: flex;
  gap: 16px;
  margin-bottom: 14px;
}
.cashback-stat {
  flex: 1;
  background: var(--navy-900);
  border-radius: var(--radius-sm);
  padding: 10px 14px;
}
.cashback-stat-val {
  font-family: var(--font-mono);
  font-size: 16px;
  font-weight: 500;
  color: var(--green-400);
  margin-bottom: 2px;
}
.cashback-stat-label {
  font-size: 10px;
  color: var(--slate-400);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.compare-toggle {
  width: 100%;
  background: rgba(255,255,255,0.04);
  border: 1px solid var(--navy-600);
  border-radius: var(--radius-md);
  color: var(--slate-300);
  font-family: var(--font-sans);
  font-size: 13px;
  padding: 10px;
  cursor: pointer;
  transition: all var(--transition);
}
.compare-toggle:hover { background: rgba(255,255,255,0.07); border-color: var(--navy-500); }
.empty-state {
  text-align: center;
  padding: 40px 20px;
  color: var(--slate-400);
  font-size: 14px;
}
@media (max-width: 560px) {
  .rec-card { padding: 18px 16px; }
  .rec-caveat { align-items: flex-start; }
}
`


export default function CardComparison({ comparisonResult }) {
  const [expandedIdx, setExpandedIdx] = useState(null)

  if (!comparisonResult) return null
  const { recommendations, routing_advice } = comparisonResult

  return (
    <>
      <style>{styles}</style>
      <div className="comparison-wrap">
        {/* Recommendations */}
        {recommendations.length === 0 ? (
          <div className="empty-state">
            No card in our catalogue beats yours for this spending.<br />
            <span style={{ color: 'var(--slate-300)' }}>Keep using it the way you are.</span>
          </div>
        ) : (
          recommendations.map((rec, i) => (
            <div key={rec.card_id} className="rec-card" style={{ animationDelay: `${i * 80}ms` }}>
              <div className="rec-rank">#{i + 1} recommendation</div>
              <div className="rec-header">
                <div className="rec-info">
                  <div className="rec-name">{rec.card_name}</div>
                  <div className="rec-bank">{rec.bank}</div>
                </div>
                <div className="rec-improvement">
                  <div
                    className="improvement-val"
                    style={rec.improvement_over_current_monthly < 0 ? { color: 'var(--slate-400)' } : {}}
                  >
                    {rec.improvement_over_current_monthly < 0 ? '−' : '+'}
                    {money(Math.abs(rec.improvement_over_current_monthly))}/mo
                  </div>
                  <div className="improvement-label">
                    {rec.improvement_over_current_monthly < 0 ? 'vs your card' : 'improvement'}
                  </div>
                </div>
              </div>

              <div className="rec-cashback-row">
                <div className="cashback-stat">
                  <div className="cashback-stat-val">{money(rec.estimated_monthly_cashback)}</div>
                  <div className="cashback-stat-label">Est. monthly</div>
                </div>
                <div className="cashback-stat">
                  <div className="cashback-stat-val">{money(rec.estimated_annual_cashback)}</div>
                  <div className="cashback-stat-label">Est. annual</div>
                </div>
              </div>

              <div className="rec-why">{rec.why_better}</div>

              <div className="rec-cats">
                {rec.best_categories.map(c => (
                  <span key={c} className="rec-cat-tag">{catLabel(c)}</span>
                ))}
              </div>

              {rec.caveat && (
                <div className="rec-caveat"><InfoIcon size={14} /> {rec.caveat}</div>
              )}
            </div>
          ))
        )}

        {/* Routing advice */}
        {routing_advice.length > 0 && (
          <div style={{ background: 'var(--navy-800)', border: '1px solid var(--navy-600)', borderRadius: 'var(--radius-md)', padding: '18px 20px' }}>
            <div style={{ fontSize: 11, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--slate-400)', marginBottom: 12 }}>
              Which card to use where
            </div>
            {routing_advice.map((tip, i) => (
              <div key={i} style={{ display: 'flex', gap: 10, marginBottom: i < routing_advice.length - 1 ? 8 : 0 }}>
                <span style={{ color: 'var(--amber-400)', flexShrink: 0, marginTop: 2 }}><ArrowRightIcon size={15} /></span>
                <span style={{ fontSize: 13, color: 'var(--slate-300)', lineHeight: 1.5 }}>{tip}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  )
}

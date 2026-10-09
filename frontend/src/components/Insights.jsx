/**
 * Insights.jsx — "What stands out" cards built from the rule-based notes the
 * spend endpoint returns. Icon and colour come from the note's kind and tone.
 */
import { CoinsIcon, RepeatIcon, TargetIcon, TrendDownIcon, TrendUpIcon } from './Icons.jsx'

const css = `
.ins-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 10px; }
.ins-card {
  display: flex; gap: 12px; align-items: flex-start; padding: 14px 16px;
  background: var(--navy-800); border: 1px solid var(--navy-700); border-radius: var(--radius-md);
  animation: fadeUp 250ms ease both;
}
.ins-icon { width: 32px; height: 32px; border-radius: 9px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; }
.ins-icon.up { background: rgba(251,146,60,0.12); color: var(--orange-400); }
.ins-icon.down { background: rgba(74,222,128,0.10); color: var(--green-400); }
.ins-icon.info { background: rgba(96,165,250,0.12); color: var(--blue-400); }
.ins-title { font-size: 14px; font-weight: 600; color: var(--white); line-height: 1.35; }
.ins-detail { font-size: 12px; color: var(--slate-400); margin-top: 3px; line-height: 1.45; }
`

function iconFor(i) {
  if (i.kind === 'recurring') return RepeatIcon
  if (i.kind === 'big_purchase') return CoinsIcon
  if (i.tone === 'up') return TrendUpIcon
  if (i.tone === 'down') return TrendDownIcon
  return TargetIcon
}

export default function Insights({ items, limit }) {
  if (!items?.length) return null
  const shown = limit ? items.slice(0, limit) : items
  return (
    <div className="ins-grid">
      <style>{css}</style>
      {shown.map((i, n) => {
        const Icon = iconFor(i)
        return (
          <div className="ins-card" key={`${i.kind}-${n}`} style={{ animationDelay: `${n * 50}ms` }}>
            <span className={`ins-icon ${i.tone}`}><Icon size={17} /></span>
            <div>
              <div className="ins-title">{i.title}</div>
              <div className="ins-detail">{i.detail}</div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

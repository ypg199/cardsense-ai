/**
 * Tabs.jsx — Material 3 style tabs, adapted to the dark theme.
 *
 *  variant="primary"   icon above the label, short rounded indicator
 *  variant="secondary" text only, indicator spans the whole tab
 *
 * Both sit on a full-width divider. Arrow keys move between tabs.
 */
const css = `
.tabs { display: flex; width: 100%; border-bottom: 1px solid var(--navy-600); position: relative; }
.tab {
  flex: 1; position: relative; background: none; border: none; cursor: pointer;
  font-family: var(--font-sans); color: var(--slate-400);
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  transition: color var(--transition), background var(--transition);
}
.tab:hover { color: var(--white); background: rgba(255,255,255,0.02); }
.tab:focus-visible { outline: 2px solid var(--amber-500); outline-offset: -2px; border-radius: 6px; }
.tab.active { color: var(--amber-400); }
.tab::after {
  content: ''; position: absolute; bottom: -1px; height: 3px;
  background: var(--amber-400); opacity: 0; transition: opacity var(--transition);
}
.tab.active::after { opacity: 1; }

.tabs-primary .tab { min-height: 64px; padding: 10px 12px 12px; gap: 4px; font-size: 14px; font-weight: 500; }
.tabs-primary .tab::after { left: 50%; transform: translateX(-50%); width: 44px; border-radius: 3px 3px 0 0; }
.tabs-primary .tab-icon { width: 24px; height: 24px; display: block; }

.tabs-secondary .tab { min-height: 48px; padding: 12px 16px; font-size: 14px; font-weight: 500; }
.tabs-secondary .tab::after { left: 0; right: 0; height: 2px; }
.tabs-secondary .tab.active { color: var(--white); }
.tabs-secondary .tab.active::after { background: var(--amber-400); }
.tab-hint { font-size: 11px; font-weight: 400; color: var(--slate-400); margin-top: 2px; }
`

export default function Tabs({ items, value, onChange, variant = 'primary', label }) {
  function onKeyDown(e) {
    const i = items.findIndex(it => it.key === value)
    if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
      e.preventDefault()
      const next = items[(i + (e.key === 'ArrowRight' ? 1 : items.length - 1)) % items.length]
      onChange(next.key)
      document.getElementById(`tab-${next.key}`)?.focus()
    }
  }
  return (
    <>
      <style>{css}</style>
      <div className={`tabs tabs-${variant}`} role="tablist" aria-label={label} onKeyDown={onKeyDown}>
        {items.map(it => {
          const active = it.key === value
          return (
            <button
              key={it.key}
              id={`tab-${it.key}`}
              role="tab"
              aria-selected={active}
              tabIndex={active ? 0 : -1}
              className={`tab${active ? ' active' : ''}`}
              onClick={() => onChange(it.key)}
            >
              {variant === 'primary' && it.icon}
              <span>{it.label}</span>
              {it.hint && <span className="tab-hint">{it.hint}</span>}
            </button>
          )
        })}
      </div>
    </>
  )
}

// Outline icons (24px, currentColor) so the active colour carries through
const icon = d => (
  <svg className="tab-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{d}</svg>
)
export const ResultsIcon = icon(<>
  <path d="M12 3a9 9 0 1 0 9 9" /><path d="M12 12l5-5" /><path d="M21 3v6h-6" />
</>)
export const AnalyseIcon = icon(<>
  <path d="M4 20V10" /><path d="M10 20V4" /><path d="M16 20v-7" /><path d="M22 20H2" />
</>)
export const CardIcon = icon(<>
  <rect x="2.5" y="5" width="19" height="14" rx="2.5" /><path d="M2.5 10h19" /><path d="M6.5 15h4" />
</>)

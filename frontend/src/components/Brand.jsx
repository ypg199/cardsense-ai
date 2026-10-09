/**
 * Brand.jsx — the logo every page shares, plus the full-page message shown
 * for a missing session, an unknown URL or an API failure.
 */
import { Link } from 'react-router-dom'
import { AlertIcon, ArrowLeftIcon, CardIcon, InfoIcon } from './Icons.jsx'

const css = `
.brand {
  display: inline-flex; align-items: center; gap: 8px;
  font-size: 13px; font-weight: 600; letter-spacing: 0.12em; text-transform: uppercase;
  color: var(--amber-400); text-decoration: none; border-radius: var(--radius-sm);
}
.brand:focus-visible { outline: 2px solid var(--amber-500); outline-offset: 4px; }
.brand-pill {
  background: rgba(245,158,11,0.08); border: 1px solid rgba(245,158,11,0.25);
  border-radius: 20px; padding: 7px 18px;
}
.brand-pill:hover { background: rgba(245,158,11,0.12); }
.sample-badge {
  display: inline-flex; align-items: center; gap: 6px; margin-left: 10px; vertical-align: middle;
  font-size: 11px; font-weight: 600; letter-spacing: 0.04em; color: var(--blue-400);
  background: rgba(96,165,250,0.1); border: 1px solid rgba(96,165,250,0.3); border-radius: 20px; padding: 3px 10px;
}

.state-page {
  min-height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 32px 24px; text-align: center; animation: fadeUp 300ms ease;
}
.state-icon {
  width: 56px; height: 56px; border-radius: 16px; margin: 28px 0 20px;
  display: flex; align-items: center; justify-content: center;
  background: rgba(245,158,11,0.08); border: 1px solid rgba(245,158,11,0.2); color: var(--amber-400);
}
.state-code { font-family: var(--font-mono); font-size: 12px; color: var(--slate-400); letter-spacing: 0.1em; margin-bottom: 8px; }
.state-title { font-family: var(--font-display); font-size: clamp(26px, 5vw, 36px); line-height: 1.2; margin-bottom: 10px; }
.state-text { font-size: 15px; color: var(--slate-300); max-width: 420px; margin-bottom: 28px; }
.state-actions { display: flex; gap: 10px; flex-wrap: wrap; justify-content: center; }
.btn-primary, .btn-ghost {
  display: inline-flex; align-items: center; gap: 8px; font-family: var(--font-sans);
  font-size: 14px; font-weight: 600; padding: 11px 20px; border-radius: var(--radius-md);
  cursor: pointer; text-decoration: none; transition: all var(--transition);
}
.btn-primary { background: var(--amber-500); color: var(--navy-950); border: 1px solid var(--amber-500); }
.btn-primary:hover { background: var(--amber-400); }
.btn-ghost { background: var(--navy-800); color: var(--slate-200); border: 1px solid var(--navy-600); }
.btn-ghost:hover { border-color: var(--amber-500); color: var(--amber-400); }
.btn-primary:focus-visible, .btn-ghost:focus-visible { outline: 2px solid var(--amber-400); outline-offset: 2px; }
`

export function Logo({ pill = false }) {
  return (
    <>
      <style>{css}</style>
      <Link to="/" className={`brand${pill ? ' brand-pill' : ''}`} aria-label="CardSense AI home">
        <CardIcon size={16} /> CardSense AI
      </Link>
    </>
  )
}

/** Marks pages built from the made-up sample statements. */
export function SampleBadge() {
  return (
    <span className="sample-badge" title="These results use made-up sample statements, not real data">
      <InfoIcon size={12} /> Sample data
    </span>
  )
}

export function StatePage({ code, title, text, actions }) {
  return (
    <>
      <style>{css}</style>
      <main className="state-page">
        <Logo />
        <div className="state-icon"><AlertIcon size={26} /></div>
        {code && <div className="state-code">{code}</div>}
        <h1 className="state-title">{title}</h1>
        <p className="state-text">{text}</p>
        <div className="state-actions">
          {actions || (
            <Link to="/" className="btn-primary"><ArrowLeftIcon size={16} /> Back to home</Link>
          )}
        </div>
      </main>
    </>
  )
}

export function SessionMissing() {
  return (
    <StatePage
      code="SESSION NOT FOUND"
      title="This analysis has expired"
      text="Results are kept for a limited time and this link no longer has any data behind it. Upload your statements again to get a fresh analysis."
      actions={<>
        <Link to="/" className="btn-primary"><ArrowLeftIcon size={16} /> Analyse a card</Link>
        <Link to="/spend" className="btn-ghost">Open Spend Analyser</Link>
      </>}
    />
  )
}

export function NotFound() {
  return (
    <StatePage
      code="404"
      title="Page not found"
      text="There's nothing at this address. Head back to the home page to analyse a card or your spending."
    />
  )
}

export function LoadFailed({ error, onRetry }) {
  if (error?.status === 404) return <SessionMissing />
  return (
    <StatePage
      code={error?.status ? `ERROR ${error.status}` : 'OFFLINE'}
      title="We couldn't load this page"
      text={error?.message || 'Something went wrong while talking to the server.'}
      actions={<>
        <button className="btn-primary" onClick={onRetry || (() => window.location.reload())}>Try again</button>
        <Link to="/" className="btn-ghost">Back to home</Link>
      </>}
    />
  )
}

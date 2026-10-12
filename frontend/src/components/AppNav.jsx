/**
 * AppNav.jsx — the two modes, always one tap away: a sticky top bar on
 * desktop (brand, mode links, theme toggle) and an app-style tab bar at the
 * bottom of the screen on phones.
 */
import { Link, useLocation } from 'react-router-dom'
import { CardIcon, ChartIcon } from './Icons.jsx'
import { Logo } from './Brand.jsx'

const css = `
.app-nav {
  position: sticky; top: 0; z-index: 40;
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
  padding: 10px 24px; background: var(--navy-950);
  border-bottom: 1px solid var(--navy-700);
}
.app-nav-links { display: flex; gap: 4px; }
.app-nav-link {
  display: inline-flex; align-items: center; gap: 8px;
  font-size: 14px; font-weight: 500; color: var(--slate-300); text-decoration: none;
  padding: 8px 14px; border-radius: var(--radius-md); transition: all var(--transition);
}
.app-nav-link:hover { color: var(--white); background: rgba(var(--tint), 0.04); }
.app-nav-link.on { color: var(--amber-400); background: rgba(245,158,11,0.12); font-weight: 600; }
.app-nav-link:focus-visible { outline: 2px solid var(--amber-400); outline-offset: 2px; }

/* The nav carries the brand on desktop, so pages drop their own copy */
@media (min-width: 721px) {
  .page-brand { display: none !important; }
}

@media (max-width: 720px) {
  .app-nav { display: none; }
  .app-tabs {
    position: fixed; left: 0; right: 0; bottom: 0; z-index: 40;
    display: grid; grid-template-columns: 1fr 1fr;
    background: var(--navy-900); border-top: 1px solid var(--navy-700);
    padding: 6px 0 calc(6px + env(safe-area-inset-bottom));
  }
  .app-tabs .app-nav-link {
    flex-direction: column; gap: 2px; font-size: 11px; padding: 4px; background: none;
    border-radius: 0; color: var(--slate-400);
  }
  .app-tabs .app-nav-link.on { color: var(--amber-400); background: none; }
  body { padding-bottom: calc(64px + env(safe-area-inset-bottom)); }
}
@media (min-width: 721px) { .app-tabs { display: none; } }
`

// Which mode a route belongs to: the quiz and results are part of the card analysis
const SPEND_ROUTES = ['/spend', '/analyser']

function Links() {
  const { pathname } = useLocation()
  const spend = SPEND_ROUTES.some(r => pathname.startsWith(r))
  return (
    <>
      <Link to="/" className={`app-nav-link${spend ? '' : ' on'}`} aria-current={spend ? undefined : 'page'}>
        <CardIcon size={18} /> Card analysis
      </Link>
      <Link to="/spend" className={`app-nav-link${spend ? ' on' : ''}`} aria-current={spend ? 'page' : undefined}>
        <ChartIcon size={18} /> Spend Analyser
      </Link>
    </>
  )
}

export default function AppNav() {
  return (
    <>
      <style>{css}</style>
      <header className="app-nav">
        <Logo />
        <nav className="app-nav-links" aria-label="Mode"><Links /></nav>
      </header>
      <nav className="app-tabs" aria-label="Mode"><Links /></nav>
    </>
  )
}

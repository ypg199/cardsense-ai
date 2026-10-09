/**
 * ThemeToggle.jsx — switches between the dark and light themes. The first
 * visit follows the system setting; a click saves the choice for next time
 * (index.html applies it before the first paint).
 */
import { useEffect, useState } from 'react'
import { MoonIcon, SunIcon } from './Icons.jsx'

const KEY = 'cs-theme'

const css = `
.theme-toggle {
  display: inline-flex; align-items: center; justify-content: center; width: 34px; height: 34px;
  border-radius: 50%; border: 1px solid var(--navy-600); background: var(--navy-800);
  color: var(--slate-300); cursor: pointer; transition: all var(--transition); flex-shrink: 0;
}
.theme-toggle:hover { border-color: var(--amber-500); color: var(--amber-400); }
.theme-toggle:focus-visible { outline: 2px solid var(--amber-400); outline-offset: 2px; }
`

function systemTheme() {
  return window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
}

export function currentTheme() {
  return document.documentElement.dataset.theme || systemTheme()
}

export default function ThemeToggle() {
  const [theme, setTheme] = useState(currentTheme)

  // Follow system changes until the visitor has made a choice
  useEffect(() => {
    const mq = window.matchMedia?.('(prefers-color-scheme: light)')
    if (!mq) return
    const onChange = () => { if (!document.documentElement.dataset.theme) setTheme(systemTheme()) }
    mq.addEventListener?.('change', onChange)
    return () => mq.removeEventListener?.('change', onChange)
  }, [])

  function toggle() {
    const next = theme === 'dark' ? 'light' : 'dark'
    document.documentElement.dataset.theme = next
    try { localStorage.setItem(KEY, next) } catch { /* private mode: the choice lasts this visit */ }
    setTheme(next)
  }

  const label = theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'
  return (
    <>
      <style>{css}</style>
      <button type="button" className="theme-toggle" onClick={toggle} aria-label={label} title={label}>
        {theme === 'dark' ? <SunIcon size={16} /> : <MoonIcon size={16} />}
      </button>
    </>
  )
}

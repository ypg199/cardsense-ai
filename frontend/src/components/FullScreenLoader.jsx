/**
 * FullScreenLoader.jsx — blocking overlay shown while the backend works.
 *
 * Steps rotate on a timer so long waits (parsing several months with the
 * model can take a minute or more) show progress instead of a frozen
 * spinner. `delay` hides it for quick calls so it doesn't flash.
 * `trivia` adds a rotating credit card fact or pun once the wait passes a
 * couple of seconds.
 */
import { useEffect, useState } from 'react'
import { shuffled } from './trivia.js'

const css = `
.fsl {
  position: fixed; inset: 0; z-index: 1000;
  display: flex; align-items: center; justify-content: center;
  background: var(--overlay);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  animation: fadeIn 200ms ease;
  padding: 24px;
}
.fsl-box { text-align: center; max-width: 380px; }
.fsl-ring {
  width: 64px; height: 64px; margin: 0 auto 24px; border-radius: 50%;
  border: 3px solid var(--navy-600); border-top-color: var(--amber-500);
  animation: spin 800ms linear infinite;
}
.fsl-title { font-family: var(--font-display); font-size: 24px; line-height: 1.25; color: var(--white); margin-bottom: 10px; }
.fsl-step { font-size: 14px; color: var(--slate-300); min-height: 22px; animation: fadeUp 300ms ease; }
.fsl-dots { display: flex; justify-content: center; gap: 6px; margin-top: 18px; }
.fsl-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--navy-600); transition: background var(--transition); }
.fsl-dot.on { background: var(--amber-500); }
.fsl-time { margin-top: 14px; font-size: 12px; color: var(--slate-400); font-family: var(--font-mono); }
.fsl-trivia-slot { margin-top: 28px; min-height: 104px; }
.fsl-trivia {
  padding: 14px 18px; border-radius: var(--radius-md); text-align: left;
  background: rgba(var(--tint), 0.04); border: 1px solid var(--navy-600);
  animation: fadeUp 300ms ease; min-height: 82px;
}
.fsl-trivia-label {
  font-size: 11px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase;
  color: var(--amber-400); margin-bottom: 4px;
}
.fsl-trivia-text { font-size: 14px; line-height: 1.5; color: var(--slate-200); }
@media (prefers-reduced-motion: reduce) {
  .fsl-trivia { animation: none; }
  .fsl-ring { animation-duration: 2400ms; }
  .fsl-step { animation: none; }
}
`

const TRIVIA_AFTER = 2 // seconds before the first item, so quick loads never show one
const TRIVIA_EVERY = 7 // seconds each item stays up

export default function FullScreenLoader({ title, steps = [], stepEvery = 6, delay = 0, showTime = false, trivia = false }) {
  const [visible, setVisible] = useState(delay === 0)
  const [seconds, setSeconds] = useState(0)
  const [items] = useState(() => (trivia ? shuffled() : []))

  useEffect(() => {
    if (delay === 0) return
    const t = setTimeout(() => setVisible(true), delay)
    return () => clearTimeout(t)
  }, [delay])

  useEffect(() => {
    const t = setInterval(() => setSeconds(s => s + 1), 1000)
    return () => clearInterval(t)
  }, [])

  if (!visible) return null

  // Advance through the steps, then stay on the last one
  const idx = steps.length ? Math.min(Math.floor(seconds / stepEvery), steps.length - 1) : -1
  const tIdx = items.length && seconds >= TRIVIA_AFTER ? Math.floor((seconds - TRIVIA_AFTER) / TRIVIA_EVERY) % items.length : -1
  const item = tIdx >= 0 ? items[tIdx] : null

  return (
    <div className="fsl" role="status" aria-live="polite" aria-busy="true">
      <style>{css}</style>
      <div className="fsl-box">
        <div className="fsl-ring" />
        <div className="fsl-title">{title}</div>
        {idx >= 0 && <div key={`step-${idx}`} className="fsl-step">{steps[idx]}</div>}
        {steps.length > 1 && (
          <div className="fsl-dots" aria-hidden="true">
            {steps.map((_, i) => <span key={i} className={`fsl-dot${i <= idx ? ' on' : ''}`} />)}
          </div>
        )}
        {showTime && seconds >= 5 && (
          <div className="fsl-time">{Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, '0')} elapsed</div>
        )}
        {items.length > 0 && (
          // Space is kept from the start so the box doesn't jump when the first item appears
          <div className="fsl-trivia-slot" aria-live="off">
            {item && (
              <div key={`trivia-${tIdx}`} className="fsl-trivia">
                <div className="fsl-trivia-label">{item.kind === 'fact' ? 'Did you know?' : 'Meanwhile'}</div>
                <div className="fsl-trivia-text">{item.text}</div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export const PARSE_STEPS = [
  'Reading your PDF statements',
  'Extracting every transaction with AI',
  'Sorting spending into categories',
  'Checking amounts and dates',
  'Almost there, a longer statement takes a little more time',
]

export const RESULT_STEPS = [
  'Calculating cashback earned and missed',
  'Scoring how well you use your card',
  'Searching for cards that fit your spending',
  'Ranking alternatives and writing tips',
]

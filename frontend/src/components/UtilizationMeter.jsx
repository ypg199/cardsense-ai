import { money } from '../format.js'
import { useEffect, useRef, useState } from 'react'

const styles = `
.meter-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}
.meter-svg { overflow: visible; }
.meter-track { fill: none; }
.meter-arc {
  fill: none;
  stroke-linecap: round;
  transition: stroke-dashoffset 600ms cubic-bezier(0.4, 0, 0.2, 1),
              stroke 400ms ease;
}
.meter-score {
  font-family: var(--font-mono);
  font-size: 42px;
  font-weight: 500;
  letter-spacing: -0.03em;
  fill: var(--white);
}
.meter-label-text {
  font-family: var(--font-sans);
  font-size: 11px;
  fill: var(--slate-400);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.meter-earned {
  font-size: 13px;
  color: var(--slate-400);
  text-align: center;
}
.meter-earned strong { color: var(--white); font-family: var(--font-mono); }
.score-label {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  padding: 3px 10px;
  border-radius: 20px;
}
.score-label.excellent { background: rgba(34,197,94,0.15); color: var(--green-400); }
.score-label.good      { background: rgba(34,197,94,0.10); color: var(--green-500); }
.score-label.average   { background: rgba(249,115,22,0.15); color: var(--orange-400); }
.score-label.below     { background: rgba(249,115,22,0.10); color: var(--orange-500); }
.score-label.poor      { background: rgba(239,68,68,0.12); color: var(--red-400); }
`

function getColor(score) {
  if (score >= 70) return '#22c55e'
  if (score >= 40) return '#f97316'
  return '#ef4444'
}

function getLabel(score) {
  if (score >= 90) return ['Excellent', 'excellent']
  if (score >= 70) return ['Good', 'good']
  if (score >= 50) return ['Average', 'average']
  if (score >= 30) return ['Below Average', 'below']
  return ['Poor', 'poor']
}

// Arc from 7-o'clock (215°) to 5-o'clock (325°) = 270° sweep
const START_ANGLE = 215
const SWEEP = 270
const R = 80
const CX = 100
const CY = 105
const STROKE = 12

function polarToXY(angleDeg, r) {
  const rad = (angleDeg - 90) * (Math.PI / 180)
  return { x: CX + r * Math.cos(rad), y: CY + r * Math.sin(rad) }
}

function describeArc(startDeg, sweepDeg, r) {
  const s = polarToXY(startDeg, r)
  const e = polarToXY(startDeg + sweepDeg, r)
  const large = sweepDeg > 180 ? 1 : 0
  return `M ${s.x} ${s.y} A ${r} ${r} 0 ${large} 1 ${e.x} ${e.y}`
}

export default function UtilizationMeter({ score = 0, earnedMonthly = 0 }) {
  const [displayed, setDisplayed] = useState(0)

  useEffect(() => {
    let frame
    const start = displayed
    const end = score
    const duration = 600
    const t0 = performance.now()

    function step(now) {
      const p = Math.min(1, (now - t0) / duration)
      const ease = p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2
      setDisplayed(Math.round(start + (end - start) * ease))
      if (p < 1) frame = requestAnimationFrame(step)
    }
    frame = requestAnimationFrame(step)
    return () => cancelAnimationFrame(frame)
  }, [score])

  const circumference = 2 * Math.PI * R
  // The track arc is SWEEP/360 of the circumference
  const trackLen = (SWEEP / 360) * circumference
  const fillLen = (displayed / 100) * trackLen
  const gapLen = circumference - fillLen

  const color = getColor(displayed)
  const [labelText, labelClass] = getLabel(displayed)
  const trackPath = describeArc(START_ANGLE, SWEEP, R)
  const fillPath = describeArc(START_ANGLE, SWEEP, R)

  return (
    <>
      <style>{styles}</style>
      <div className="meter-wrap">
        <svg className="meter-svg" width="200" height="190" viewBox="0 0 200 190">
          {/* Track */}
          <path
            className="meter-track"
            d={trackPath}
            stroke="rgba(255,255,255,0.07)"
            strokeWidth={STROKE}
            strokeLinecap="round"
          />
          {/* Fill arc — use dasharray trick */}
          <path
            className="meter-arc"
            d={fillPath}
            stroke={color}
            strokeWidth={STROKE}
            strokeDasharray={`${fillLen} ${circumference}`}
            strokeDashoffset={0}
            style={{ filter: `drop-shadow(0 0 8px ${color}60)` }}
          />
          {/* Score text */}
          <text
            className="meter-score"
            x={CX}
            y={CY + 6}
            textAnchor="middle"
            dominantBaseline="middle"
          >
            {displayed}
          </text>
          <text
            className="meter-label-text"
            x={CX}
            y={CY + 30}
            textAnchor="middle"
          >
            / 100
          </text>
        </svg>

        <span className={`score-label ${labelClass}`}>{labelText}</span>

        {earnedMonthly > 0 && (
          <p className="meter-earned">
            Earning <strong>{money(earnedMonthly)}</strong>/month in cashback
          </p>
        )}
      </div>
    </>
  )
}

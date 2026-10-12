/**
 * GetStarted.jsx — the landing page's two ways in: a one-tap demo on the
 * sample statements, or the visitor's own statement, plus a short
 * "how it works" strip so first-time visitors know what they need and get.
 */
import { Link } from 'react-router-dom'
import { ArrowRightIcon, FileIcon } from './Icons.jsx'
import { SAMPLE_MONTHS } from './SampleBanner.jsx'

const MONTH_NAMES = { '01': 'Jan', '02': 'Feb', '03': 'Mar', '04': 'Apr' }

const STEPS = [
  { title: 'Pick your card', text: 'Search by bank or card name' },
  { title: 'Upload a statement', text: 'The PDF your bank emails you' },
  { title: 'Answer a few questions', text: 'Quick yes or no taps' },
  { title: 'Get your results', text: 'Score, missed cashback, a better card' },
]

const css = `
.get-started { margin: 28px auto 0; max-width: 640px; }
.gs-actions { display: flex; gap: 12px; justify-content: center; flex-wrap: wrap; }
.gs-demo, .gs-own {
  display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  border-radius: var(--radius-md); padding: 14px 22px;
  font-family: var(--font-sans); font-size: 15px; font-weight: 700; cursor: pointer;
  transition: all var(--transition); text-decoration: none;
}
.gs-demo {
  background: linear-gradient(135deg, var(--amber-500), var(--amber-400));
  color: var(--on-accent); border: none;
}
.gs-demo:hover:not(:disabled) { transform: translateY(-2px); box-shadow: 0 12px 40px rgba(245,158,11,0.35); }
.gs-demo:disabled { opacity: 0.5; cursor: not-allowed; }
.gs-own {
  background: var(--navy-800); color: var(--white);
  border: 1px solid var(--navy-600); font-weight: 600;
}
.gs-own:hover { border-color: var(--amber-400); }
.gs-demo:focus-visible, .gs-own:focus-visible { outline: 2px solid var(--amber-400); outline-offset: 2px; }
.gs-spend { font-size: 13px; color: var(--slate-400); margin-top: 14px; }
.gs-spend a { color: var(--amber-400); font-weight: 600; text-decoration: none; }
.gs-spend a:hover { text-decoration: underline; }
.gs-note { font-size: 12px; color: var(--slate-400); margin-top: 10px; }
.gs-note a { color: var(--slate-300); text-decoration: underline; text-underline-offset: 2px; }
.gs-note a:hover { color: var(--amber-400); }

.gs-steps {
  list-style: none; display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px;
  margin-top: 28px; text-align: left; counter-reset: gs;
}
.gs-step {
  counter-increment: gs; padding: 12px; border-radius: var(--radius-md);
  background: rgba(var(--tint), 0.03); border: 1px solid var(--navy-700);
}
.gs-step::before {
  content: counter(gs); display: inline-flex; align-items: center; justify-content: center;
  width: 22px; height: 22px; border-radius: 50%; margin-bottom: 6px;
  background: rgba(245,158,11,0.15); border: 1px solid rgba(245,158,11,0.4);
  color: var(--amber-400); font-size: 11px; font-weight: 700;
}
.gs-step strong { display: block; font-size: 13px; color: var(--white); }
.gs-step span { display: block; font-size: 12px; color: var(--slate-400); line-height: 1.4; margin-top: 2px; }
.gs-privacy { font-size: 12px; color: var(--slate-400); margin-top: 14px; }

@media (max-width: 560px) {
  .gs-demo, .gs-own { width: 100%; }
  .gs-steps { grid-template-columns: 1fr 1fr; }
}
`

export default function GetStarted({ onDemo, disabled, ownTarget = 'own-statement' }) {
  function scrollToOwn(e) {
    e.preventDefault()
    document.getElementById(ownTarget)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
  return (
    <div className="get-started">
      <style>{css}</style>
      <div className="gs-actions">
        <button type="button" className="gs-demo" onClick={onDemo} disabled={disabled}>
          <FileIcon size={16} /> Try a demo, no upload needed <ArrowRightIcon size={15} />
        </button>
        <a href={`#${ownTarget}`} className="gs-own" onClick={scrollToOwn}>
          Use my own statement ↓
        </a>
      </div>
      <p className="gs-spend">
        Just want charts of your spending? <Link to="/spend">Open the Spend Analyser →</Link>
      </p>
      <p className="gs-note">
        The demo uses four months of a made-up HDFC Millennia statement. You can also download
        the sample PDFs (
        {SAMPLE_MONTHS.map((m, i) => (
          <span key={m}>
            {i > 0 && ', '}
            <a href={`/samples/hdfc_millennia_${m}.pdf`} download>{MONTH_NAMES[m.slice(5)]}</a>
          </span>
        ))}
        ) to try the upload.
      </p>

      <ol className="gs-steps" aria-label="How it works">
        {STEPS.map(s => (
          <li key={s.title} className="gs-step">
            <strong>{s.title}</strong>
            <span>{s.text}</span>
          </li>
        ))}
      </ol>
      <p className="gs-privacy">
        Your PDF is read once and not kept. Results are deleted after 24 hours.
      </p>
    </div>
  )
}

/**
 * SampleBanner.jsx — "try it with sample data" strip on both upload pages,
 * so the app can be explored without uploading a real statement.
 */
import { ArrowRightIcon, FileIcon } from './Icons.jsx'

export const SAMPLE_MONTHS = ['2026-01', '2026-02', '2026-03', '2026-04']
const MONTH_NAMES = { '01': 'Jan', '02': 'Feb', '03': 'Mar', '04': 'Apr' }

const css = `
.sample-banner {
  display: flex; align-items: center; gap: 14px 20px; flex-wrap: wrap;
  margin: 28px auto 0; max-width: 640px; padding: 14px 16px 14px 18px; text-align: left;
  border: 1px dashed rgba(245,158,11,0.35); border-radius: var(--radius-lg); background: rgba(245,158,11,0.04);
}
.sample-copy { flex: 1 1 260px; min-width: 0; }
.sample-title { font-size: 14px; font-weight: 600; color: var(--white); }
.sample-text { font-size: 12px; color: var(--slate-400); margin-top: 2px; }
.sample-text a { color: var(--slate-300); text-decoration: underline; text-underline-offset: 2px; }
.sample-text a:hover { color: var(--amber-400); }
.sample-text a:focus-visible { outline: 2px solid var(--amber-400); border-radius: 2px; }
.sample-btn {
  display: inline-flex; align-items: center; gap: 8px; white-space: nowrap;
  background: var(--navy-800); border: 1px solid rgba(245,158,11,0.5); color: var(--amber-400);
  border-radius: var(--radius-md); padding: 10px 16px; font-family: var(--font-sans); font-size: 14px; font-weight: 600;
  cursor: pointer; transition: all var(--transition);
}
.sample-btn:hover:not(:disabled) { background: rgba(245,158,11,0.1); border-color: var(--amber-400); }
.sample-btn:focus-visible { outline: 2px solid var(--amber-400); outline-offset: 2px; }
.sample-btn:disabled { opacity: 0.5; cursor: not-allowed; }
@media (max-width: 560px) { .sample-btn { width: 100%; justify-content: center; } }
`

export default function SampleBanner({ onTry, disabled, label = 'Try it with sample data' }) {
  return (
    <div className="sample-banner">
      <style>{css}</style>
      <div className="sample-copy">
        <div className="sample-title">No statement handy?</div>
        <div className="sample-text">
          Use four months of a made-up HDFC Millennia statement, or download the sample PDFs (
          {SAMPLE_MONTHS.map((m, i) => (
            <span key={m}>
              {i > 0 && ', '}
              <a href={`/samples/hdfc_millennia_${m}.pdf`} download>{MONTH_NAMES[m.slice(5)]}</a>
            </span>
          ))}
          ) and upload them yourself.
        </div>
      </div>
      <button type="button" className="sample-btn" onClick={onTry} disabled={disabled}>
        <FileIcon size={16} /> {label} <ArrowRightIcon size={15} />
      </button>
    </div>
  )
}

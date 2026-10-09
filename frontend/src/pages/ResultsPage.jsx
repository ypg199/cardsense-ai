import { useState, useEffect } from 'react'
import { useParams, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import CashbackBreakdown from '../components/CashbackBreakdown.jsx'
import CardComparison from '../components/CardComparison.jsx'
import UtilizationMeter from '../components/UtilizationMeter.jsx'
import { getSessionStatus } from '../api.js'
import FullScreenLoader, { RESULT_STEPS } from '../components/FullScreenLoader.jsx'
import { SpendAnalyser } from './SpendAnalyserPage.jsx'

const css = `
.results-page {
  min-height: 100vh;
  max-width: 960px;
  margin: 0 auto;
  padding: 32px 24px 80px;
}
.results-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 40px;
  animation: fadeUp 300ms ease;
}
.results-logo {
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--amber-400);
}
.new-analysis-btn {
  background: var(--navy-800);
  border: 1px solid var(--navy-600);
  border-radius: var(--radius-md);
  color: var(--slate-300);
  font-family: var(--font-sans);
  font-size: 13px;
  padding: 9px 18px;
  cursor: pointer;
  transition: all var(--transition);
}
.new-analysis-btn:hover { border-color: var(--amber-500); color: var(--amber-400); }
.view-tabs {
  display: flex;
  gap: 4px;
  padding: 4px;
  background: var(--navy-900);
  border: 1px solid var(--navy-700);
  border-radius: 14px;
  width: fit-content;
  margin: 0 auto 8px;
  animation: fadeUp 300ms ease;
}
.view-tab {
  border: none;
  background: transparent;
  color: var(--slate-400);
  font-family: var(--font-sans);
  font-size: 14px;
  font-weight: 500;
  padding: 10px 22px;
  border-radius: 10px;
  cursor: pointer;
  transition: all var(--transition);
}
.view-tab:hover { color: var(--white); }
.view-tab.active { background: var(--navy-700); color: var(--amber-400); box-shadow: 0 1px 0 rgba(255,255,255,0.04) inset; }
.view-tab:focus-visible { outline: 2px solid var(--amber-500); outline-offset: 2px; }

.hero-section {
  text-align: center;
  padding: 48px 0 40px;
  animation: fadeUp 350ms ease;
}
.hero-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: rgba(245,158,11,0.08);
  border: 1px solid rgba(245,158,11,0.25);
  border-radius: 20px;
  padding: 6px 18px;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--amber-400);
  margin-bottom: 24px;
}
.hero-title {
  font-family: var(--font-display);
  font-size: clamp(28px, 5vw, 44px);
  line-height: 1.15;
  letter-spacing: -0.02em;
  margin-bottom: 12px;
}
.hero-subtitle {
  font-size: 15px;
  color: var(--slate-400);
  max-width: 480px;
  margin: 0 auto 32px;
}

.scores-row {
  display: flex;
  justify-content: center;
  gap: 24px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.results-section {
  background: var(--navy-900);
  border: 1px solid var(--navy-700);
  border-radius: var(--radius-xl);
  padding: 28px;
  margin-bottom: 20px;
  animation: fadeUp 400ms ease both;
}
.rs-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 24px;
}
.rs-icon {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: rgba(245,158,11,0.1);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  flex-shrink: 0;
}
.rs-title { font-size: 17px; font-weight: 600; color: var(--white); }
.rs-subtitle { font-size: 12px; color: var(--slate-400); margin-top: 2px; }

.tips-grid { display: flex; flex-direction: column; gap: 12px; }
.tip-card {
  display: flex;
  gap: 14px;
  background: rgba(255,255,255,0.03);
  border: 1px solid var(--navy-700);
  border-radius: var(--radius-md);
  padding: 16px;
  animation: fadeUp 200ms ease both;
}
.tip-icon { font-size: 20px; flex-shrink: 0; }
.tip-text { font-size: 13px; color: var(--slate-300); line-height: 1.55; }

.multi-card-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}
.mc-tab {
  padding: 8px 16px;
  border-radius: 20px;
  border: 1px solid var(--navy-600);
  background: var(--navy-800);
  color: var(--slate-400);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition);
}
.mc-tab:hover { border-color: var(--navy-500); color: var(--white); }
.mc-tab.active { border-color: var(--amber-500); color: var(--amber-400); background: rgba(245,158,11,0.06); }

.loading-full {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 80vh;
  gap: 20px;
}
.spinner-xl {
  width: 56px;
  height: 56px;
  border: 3px solid var(--navy-600);
  border-top-color: var(--amber-500);
  border-radius: 50%;
  animation: spin 800ms linear infinite;
}

.tip-icons = ['💡', '🎯', '📊', '⚡', '💰']
`

const TIP_ICONS = ['💡', '🎯', '📊', '⚡', '💰']

export default function ResultsPage() {
  const { sessionId } = useParams()
  const location = useLocation()
  const navigate = useNavigate()

  const [session, setSession] = useState(location.state?.session || null)
  const [loading, setLoading] = useState(!location.state?.session)
  const [activeCard, setActiveCard] = useState(0)
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') === 'analyse' ? 'analyse' : 'results'
  const setTab = t => setParams(t === 'results' ? {} : { tab: t }, { replace: true })

  useEffect(() => {
    if (!session) {
      getSessionStatus(sessionId)
        .then(s => { setSession(s); setLoading(false) })
        .catch(() => setLoading(false))
    }
  }, [sessionId])

  if (loading) return <FullScreenLoader title="Loading your results" steps={['Fetching your analysis']} />

  if (!session) return null

  const { cards, comparison_result , cashback_result} = session
  const card = cards[activeCard] || cards[0]
  const cr = card?.cashback_result
  const comp = comparison_result
  const tips = comp?.tips || []
  const earnedTotal = cr ? Object.values(cr.earned_breakdown || {}).reduce((s, v) => s + v, 0) : 0
  const missedTotal = cr ? Object.values(cr.missed_breakdown || {}).reduce((s, v) => s + v, 0) : 0

  return (
    <>
      <style>{css}</style>
      <div className="results-page">
        <div className="results-header">
          <div className="results-logo">💳 CardSense AI</div>
          <button className="new-analysis-btn" onClick={() => navigate('/')}>
            ← New Analysis
          </button>
        </div>

        <div className="view-tabs" role="tablist" aria-label="Results views">
          {[['results', '📊 Results'], ['analyse', '📈 Analyse spending']].map(([key, label]) => (
            <button
              key={key}
              role="tab"
              aria-selected={tab === key}
              className={`view-tab${tab === key ? ' active' : ''}`}
              onClick={() => setTab(key)}
            >
              {label}
            </button>
          ))}
        </div>

        {tab === 'analyse' ? (
          <SpendAnalyser sessionId={sessionId} showTitle={false} />
        ) : (
          <>

          {/* Hero */}
          <div className="hero-section">
            <div className="hero-badge">
              📊 Analysis Complete
            </div>
            <h1 className="hero-title">
              {comp?.verdict === 'Good fit'
                ? "You're getting good value"
                : comp?.verdict === 'Switch recommended'
                ? "Time for a better card"
                : "Room to do better"}
            </h1>
            <p className="hero-subtitle">
              {comp?.verdict_reason || `You earned ₹${earnedTotal.toFixed(0)} and missed ₹${missedTotal.toFixed(0)} in cashback.`}
            </p>

            {/* Score meters per card */}
            <div className="scores-row">
              {cards.map((c, i) => (
                <div key={c.card_id} style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: 11, color: 'var(--slate-400)', marginBottom: 8, letterSpacing: '0.06em', textTransform: 'uppercase' }}>
                    {c.card_name.split(' ').slice(-2).join(' ')}
                  </div>
                  <UtilizationMeter
                    score={cashback_result?.utilization_score || 0}
                    earnedMonthly={Object.values(cashback_result?.earned_breakdown || {}).reduce((s, v) => s + v, 0)}
                  />
                </div>
              ))}
            </div>
          </div>

          {/* Multi-card tabs for breakdown */}
          {cards.length > 1 && (
            <div className="multi-card-tabs">
              {cards.map((c, i) => (
                <button
                  key={c.card_id}
                  className={`mc-tab${i === activeCard ? ' active' : ''}`}
                  onClick={() => setActiveCard(i)}
                >
                  {c.card_name}
                </button>
              ))}
            </div>
          )}

          {/* Section B: Cashback Breakdown */}
          <div className="results-section" style={{ animationDelay: '80ms' }}>
            <div className="rs-header">
              <div className="rs-icon">📊</div>
              <div>
                <div className="rs-title">Cashback Breakdown</div>
                <div className="rs-subtitle">{card?.card_name} — Earned vs. Potential</div>
              </div>
            </div>
            <CashbackBreakdown cashbackResult={cr} multiMonth={card?.months?.length > 1} />
          </div>

          {/* Section C: Card Comparison */}
          {comp && (
            <div className="results-section" style={{ animationDelay: '140ms' }}>
              <div className="rs-header">
                <div className="rs-icon">🔄</div>
                <div>
                  <div className="rs-title">Better Card Alternatives</div>
                  <div className="rs-subtitle">Cards that could earn you more based on your spend</div>
                </div>
              </div>
              <CardComparison comparisonResult={comp} />
            </div>
          )}

          {/* Section D: Tips */}
          {tips.length > 0 && (
            <div className="results-section" style={{ animationDelay: '200ms' }}>
              <div className="rs-header">
                <div className="rs-icon">💡</div>
                <div>
                  <div className="rs-title">Actionable Tips</div>
                  <div className="rs-subtitle">Personalised to your spending pattern</div>
                </div>
              </div>
              <div className="tips-grid">
                {tips.map((tip, i) => (
                  <div key={i} className="tip-card" style={{ animationDelay: `${i * 60}ms` }}>
                    <span className="tip-icon">{TIP_ICONS[i % TIP_ICONS.length]}</span>
                    <p className="tip-text">{tip}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
          </>
        )}
      </div>
    </>
  )
}

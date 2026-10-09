import { useState, useEffect } from 'react'
import { useParams, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import CashbackBreakdown from '../components/CashbackBreakdown.jsx'
import CardComparison from '../components/CardComparison.jsx'
import CardCompareTable from '../components/CardCompareTable.jsx'
import Insights from '../components/Insights.jsx'
import UtilizationMeter from '../components/UtilizationMeter.jsx'
import { getSessionStatus, getSpendSummary, reportUrl } from '../api.js'
import FullScreenLoader, { RESULT_STEPS } from '../components/FullScreenLoader.jsx'
import { SpendAnalyser } from './SpendAnalyserPage.jsx'
import Tabs, { AnalyseIcon, ResultsIcon } from '../components/Tabs.jsx'
import { Logo, LoadFailed, SampleBadge } from '../components/Brand.jsx'
import { ArrowLeftIcon, BulbIcon, DownloadIcon, CardIcon, ChartIcon, CheckCircleIcon, CoinsIcon, SparkIcon, SwapIcon, TargetIcon } from '../components/Icons.jsx'
import { money } from '../format.js'

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
.new-analysis-btn {
  background: var(--navy-800);
  border: 1px solid var(--navy-600);
  border-radius: var(--radius-md);
  color: var(--slate-300);
  font-family: var(--font-sans);
  font-size: 13px;
  padding: 9px 18px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: all var(--transition);
}
.results-header { gap: 12px; }
.new-analysis-btn { white-space: nowrap; text-decoration: none; }
.results-actions { display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
.new-analysis-btn:focus-visible { outline: 2px solid var(--amber-400); outline-offset: 2px; }
.new-analysis-btn:hover { border-color: var(--amber-500); color: var(--amber-400); }
.results-tabs { margin-bottom: 24px; animation: fadeUp 300ms ease; }

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
  color: var(--amber-400);
  flex-shrink: 0;
}
.rs-title { font-size: 17px; font-weight: 600; color: var(--white); }
.rs-subtitle { font-size: 12px; color: var(--slate-400); margin-top: 2px; }

.link-btn {
  margin-top: 14px; background: none; border: none; padding: 0; cursor: pointer;
  color: var(--amber-400); font-family: var(--font-sans); font-size: 13px; font-weight: 500;
}
.link-btn:hover { text-decoration: underline; }
.link-btn:focus-visible { outline: 2px solid var(--amber-400); outline-offset: 2px; border-radius: 2px; }
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
.tip-icon { flex-shrink: 0; color: var(--amber-400); margin-top: 1px; }
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

@media (max-width: 560px) {
  .results-page { padding: 24px 16px 60px; }
  .results-header { margin-bottom: 24px; }
  .hero-section { padding: 32px 0 24px; }
  .results-section { padding: 20px 16px; border-radius: var(--radius-lg); }
  .rs-header { margin-bottom: 18px; }
}
.meter-card-name {
  font-size: 12px; color: var(--slate-300); margin-bottom: 8px; font-weight: 500;
  max-width: 220px; margin-left: auto; margin-right: auto;
}
`

// The headline follows the verdict, which the backend derives from the
// score and the best alternative, so a high score never reads as a failure.
function headline(verdict, score) {
  if (verdict === 'Good fit') return "You're getting good value"
  if (verdict === 'Switch recommended') {
    return score >= 70 ? "You're using it well, but a better card exists" : 'Time for a better card'
  }
  return 'Room to do better'
}

function monthlyEarned(cr, months) {
  if (!cr) return 0
  const total = Object.values(cr.earned_breakdown || {}).reduce((s, v) => s + v, 0)
  const n = Math.max(cr.monthly_breakdown?.length || 0, months?.length || 0, 1)
  return total / n
}

const TIP_ICONS = [BulbIcon, TargetIcon, ChartIcon, CoinsIcon]

export default function ResultsPage() {
  const { sessionId } = useParams()
  const location = useLocation()
  const navigate = useNavigate()

  const [session, setSession] = useState(location.state?.session || null)
  const [loading, setLoading] = useState(!location.state?.session)
  const [loadError, setLoadError] = useState(null)
  const [insights, setInsights] = useState([])

  // Spending notes come from the same endpoint as the analyser; optional
  useEffect(() => {
    getSpendSummary(sessionId).then(d => setInsights(d.insights || [])).catch(() => {})
  }, [sessionId])
  const [activeCard, setActiveCard] = useState(0)
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') === 'analyse' ? 'analyse' : 'results'
  const setTab = t => setParams(t === 'results' ? {} : { tab: t }, { replace: true })

  useEffect(() => {
    if (!session) {
      getSessionStatus(sessionId)
        .then(s => { setSession(s); setLoading(false) })
        .catch(e => { setLoadError(e); setLoading(false) })
    }
  }, [sessionId])

  if (loading) return <FullScreenLoader title="Loading your results" steps={['Fetching your analysis']} />

  if (!session) return <LoadFailed error={loadError} />

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
          <div><Logo />{session.sample && <SampleBadge />}</div>
          <div className="results-actions">
            <a className="new-analysis-btn" href={reportUrl(sessionId)} download>
              <DownloadIcon size={15} /> PDF report
            </a>
            <button className="new-analysis-btn" onClick={() => navigate('/')}>
              <ArrowLeftIcon size={15} /> New analysis
            </button>
          </div>
        </div>

        <div className="results-tabs">
          <Tabs
            label="Results views"
            value={tab}
            onChange={setTab}
            items={[
              { key: 'results', label: 'Results', icon: ResultsIcon },
              { key: 'analyse', label: 'Analyse spending', icon: AnalyseIcon },
            ]}
          />
        </div>

        {tab === 'analyse' ? (
          <SpendAnalyser sessionId={sessionId} showTitle={false} />
        ) : (
          <>

          {/* Hero */}
          <div className="hero-section">
            <div className="hero-badge">
              <CheckCircleIcon size={15} /> Analysis complete
            </div>
            <h1 className="hero-title">
              {headline(comp?.verdict, comp?.card_score ?? cashback_result?.utilization_score ?? 0)}
            </h1>
            <p className="hero-subtitle">
              {comp?.verdict_reason || `You earned ${money(earnedTotal)} and missed ${money(missedTotal)} in cashback.`}
            </p>

            {/* Score meters per card */}
            <div className="scores-row">
              {cards.map((c, i) => (
                <div key={c.card_id} style={{ textAlign: 'center' }}>
                  <div className="meter-card-name">{c.card_name}</div>
                  <UtilizationMeter
                    score={(c.cashback_result || cashback_result)?.utilization_score || 0}
                    earnedMonthly={monthlyEarned(c.cashback_result || cashback_result, c.months)}
                  />
                </div>
              ))}
            </div>
          </div>

          {insights.length > 0 && (
            <div className="results-section" style={{ animationDelay: '40ms' }}>
              <div className="rs-header">
                <div className="rs-icon"><SparkIcon size={18} /></div>
                <div>
                  <div className="rs-title">What stands out</div>
                  <div className="rs-subtitle">Patterns in your spending across these statements</div>
                </div>
              </div>
              <Insights items={insights} limit={3} />
              <button className="link-btn" onClick={() => setTab('analyse')}>See all your spending charts</button>
            </div>
          )}

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
              <div className="rs-icon"><ChartIcon size={18} /></div>
              <div>
                <div className="rs-title">Cashback breakdown</div>
                <div className="rs-subtitle">{card?.card_name}: earned vs. possible</div>
              </div>
            </div>
            <CashbackBreakdown cashbackResult={cr} multiMonth={card?.months?.length > 1} />
          </div>

          {/* Side-by-side comparison on the user's own spending */}
          {comp?.comparison?.cards?.length > 1 && (
            <div className="results-section" style={{ animationDelay: '110ms' }}>
              <div className="rs-header">
                <div className="rs-icon"><CardIcon size={18} /></div>
                <div>
                  <div className="rs-title">Your card vs the alternatives</div>
                  <div className="rs-subtitle">What each card would pay you on your actual monthly spending</div>
                </div>
              </div>
              <CardCompareTable comparison={comp.comparison} />
            </div>
          )}

          {/* Section C: Card Comparison */}
          {comp && (
            <div className="results-section" style={{ animationDelay: '140ms' }}>
              <div className="rs-header">
                <div className="rs-icon"><SwapIcon size={18} /></div>
                <div>
                  <div className="rs-title">Better card alternatives</div>
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
                <div className="rs-icon"><BulbIcon size={18} /></div>
                <div>
                  <div className="rs-title">Actionable tips</div>
                  <div className="rs-subtitle">Personalised to your spending pattern</div>
                </div>
              </div>
              <div className="tips-grid">
                {tips.map((tip, i) => {
                  const TipIcon = TIP_ICONS[i % TIP_ICONS.length]
                  return (
                  <div key={i} className="tip-card" style={{ animationDelay: `${i * 60}ms` }}>
                    <span className="tip-icon"><TipIcon size={18} /></span>
                    <p className="tip-text">{tip}</p>
                  </div>
                  )
                })}
              </div>
            </div>
          )}
          </>
        )}
      </div>
    </>
  )
}

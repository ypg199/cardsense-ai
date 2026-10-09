import { useState, useEffect, useCallback } from 'react'
import { useParams, useLocation, useNavigate } from 'react-router-dom'
import QuestionCard from '../components/QuestionCard.jsx'
import UtilizationMeter from '../components/UtilizationMeter.jsx'
import { submitAnswer, getSessionStatus } from '../api.js'

const css = `
.util-page {
  min-height: 100vh;
  max-width: 960px;
  margin: 0 auto;
  padding: 32px 24px 60px;
}
.util-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 36px;
  animation: fadeUp 300ms ease;
}
.util-logo {
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--amber-400);
}
.util-progress-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: var(--slate-400);
}
.progress-track {
  width: 120px;
  height: 4px;
  background: var(--navy-700);
  border-radius: 2px;
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  background: var(--amber-500);
  border-radius: 2px;
  transition: width 400ms ease;
}
.util-layout {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 24px;
  align-items: start;
}
@media (max-width: 680px) {
  .util-layout { grid-template-columns: 1fr; }
}
.left-panel {
  position: sticky;
  top: 24px;
  background: var(--navy-900);
  border: 1px solid var(--navy-700);
  border-radius: var(--radius-xl);
  padding: 24px 20px;
  animation: fadeUp 350ms ease;
}
.card-info-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--white);
  margin-bottom: 4px;
}
.card-info-bank {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--amber-400);
  margin-bottom: 20px;
}
.meter-section { margin-bottom: 24px; }
.auto-detected {
  margin-top: 16px;
  border-top: 1px solid var(--navy-700);
  padding-top: 14px;
}
.auto-detected-title {
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--slate-400);
  margin-bottom: 8px;
}
.auto-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--slate-400);
  margin-bottom: 6px;
}
.auto-check { color: var(--green-400); font-size: 14px; }

.right-panel { animation: fadeUp 400ms ease; }
.question-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}
.q-counter {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--slate-400);
}
.q-counter span { color: var(--white); font-weight: 500; }

.answered-section {
  margin-top: 20px;
  background: var(--navy-900);
  border: 1px solid var(--navy-700);
  border-radius: var(--radius-lg);
  overflow: hidden;
}
.answered-toggle {
  width: 100%;
  background: none;
  border: none;
  color: var(--slate-400);
  font-family: var(--font-sans);
  font-size: 12px;
  letter-spacing: 0.06em;
  padding: 12px 16px;
  cursor: pointer;
  text-align: left;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.answered-list { padding: 0 16px 12px; }
.answered-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 0;
  border-bottom: 1px solid rgba(255,255,255,0.04);
  font-size: 12px;
  color: var(--slate-400);
}
.answered-item:last-child { border-bottom: none; }
.answered-icon { flex-shrink: 0; margin-top: 1px; }

.card-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 24px;
  flex-wrap: wrap;
}
.card-tab {
  padding: 8px 16px;
  border-radius: 20px;
  border: 1px solid var(--navy-600);
  background: var(--navy-800);
  color: var(--slate-400);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition);
  display: flex;
  align-items: center;
  gap: 6px;
}
.card-tab:hover { border-color: var(--navy-500); color: var(--white); }
.card-tab.active { border-color: var(--amber-500); color: var(--amber-400); background: rgba(245,158,11,0.06); }
.card-tab .score-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--green-500);
}

.loading-overlay {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 300px;
  gap: 16px;
}
.spinner-lg {
  width: 48px;
  height: 48px;
  border: 3px solid var(--navy-600);
  border-top-color: var(--amber-500);
  border-radius: 50%;
  animation: spin 800ms linear infinite;
}
.loading-text { color: var(--slate-400); font-size: 14px; }
`

export default function UtilizationPage() {
  const { sessionId } = useParams()
  const location = useLocation()
  const navigate = useNavigate()

  const [session, setSession] = useState(location.state?.session || null)
  const [loading, setLoading] = useState(!location.state?.session)
  const [answerLoading, setAnswerLoading] = useState(false)
  const [showAnswered, setShowAnswered] = useState(false)
  const [activeTab, setActiveTab] = useState(0)

  const poll = useCallback(async () => {
    try {
      const s = await getSessionStatus(sessionId)
      setSession(s)
      if (s.ui_action === 'show_results') {
        navigate(`/results/${sessionId}`, { state: { session: s } })
      }
    } catch (e) {
      console.error('Poll error', e)
    }
  }, [sessionId, navigate])

  useEffect(() => {
    if (!session) { poll().finally(() => setLoading(false)); return }
    if (session.ui_action === 'show_loading') {
      const t = setInterval(poll, 2000)
      return () => clearInterval(t)
    }
  }, [session?.ui_action, poll])

  async function handleAnswer(questionId, answer) {
    setAnswerLoading(true)
    try {
      const resp = await submitAnswer(sessionId, {
        question_id: questionId,
        answer,
        card_idx: session.current_card_idx || 0,
      })
      setSession(resp)
      if (resp.ui_action === 'show_results') {
        navigate(`/results/${sessionId}`, { state: { session: resp } })
      }
    } catch (e) {
      console.error('Answer error', e)
    } finally {
      setAnswerLoading(false)
    }
  }

  if (loading) return (
    <>
      <style>{css}</style>
      <div className="util-page">
        <div className="loading-overlay">
          <div className="spinner-lg" />
          <p className="loading-text">Loading your analysis…</p>
        </div>
      </div>
    </>
  )

  if (!session) return null

  const { current_question, questions_answered, questions_total, cards, current_card_idx } = session
  const activeCard = cards[current_card_idx] || cards[0]
  const progress = questions_total > 0 ? (questions_answered / questions_total) * 100 : 0
  const cr = activeCard?.cashback_result
  const score = cr?.utilization_score || 0
  const earned = cr ? Object.values(cr.earned_breakdown || {}).reduce((s, v) => s + v, 0) : 0

  return (
    <>
      <style>{css}</style>
      <div className="util-page">
        <div className="util-header">
          <div className="util-logo">💳 CardSense</div>
          <div className="util-progress-wrap">
            <span className="mono" style={{ fontSize: 12 }}>{questions_answered}/{questions_total}</span>
            <div className="progress-track">
              <div className="progress-fill" style={{ width: `${progress}%` }} />
            </div>
          </div>
        </div>

        {/* Multi-card tabs */}
        {cards.length > 1 && (
          <div className="card-tabs">
            {cards.map((c, i) => (
              <button
                key={c.card_id}
                className={`card-tab${i === (current_card_idx || 0) ? ' active' : ''}`}
                onClick={() => setActiveTab(i)}
              >
                {c.card_name}
                {c.cashback_result && <span className="score-dot" />}
              </button>
            ))}
          </div>
        )}

        <div className="util-layout">
          {/* Left panel */}
          <div className="left-panel">
            <div className="card-info-bank">{activeCard?.card_name?.split(' ')[0] || 'Your Card'}</div>
            <div className="card-info-name">{activeCard?.card_name}</div>

            {/*<div className="meter-section">
              <UtilizationMeter score={score} earnedMonthly={earned} />
            </div>*/}

            {/* Auto-detected */}
            {questions_answered > 0 && (
              <div className="auto-detected">
                <div className="auto-detected-title">Auto-detected from statements</div>
                {Array.from({ length: Math.min(questions_answered, 4) }).map((_, i) => (
                  <div key={i} className="auto-item">
                    <span className="auto-check">✓</span>
                    <span>Usage confirmed automatically</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Right panel */}
          <div className="right-panel">
            {session.ui_action === 'show_loading' ? (
              <div className="loading-overlay">
                <div className="spinner-lg" />
                <p className="loading-text">Calculating your cashback…</p>
              </div>
            ) : current_question ? (
              <>
                <div className="question-header">
                  <span className="q-counter">
                    Question <span>{questions_answered + 1}</span> of <span>{questions_total}</span>
                  </span>
                </div>

                <QuestionCard
                  question={current_question}
                  onAnswer={handleAnswer}
                  loading={answerLoading}
                />

                {questions_answered > 0 && (
                  <div className="answered-section" style={{ marginTop: 16 }}>
                    <button
                      className="answered-toggle"
                      onClick={() => setShowAnswered(s => !s)}
                    >
                      <span>Already answered ({questions_answered})</span>
                      <span>{showAnswered ? '▲' : '▼'}</span>
                    </button>
                    {showAnswered && (
                      <div className="answered-list">
                        <div className="answered-item">
                          <span className="answered-icon">ℹ</span>
                          <span>Previous answers have been recorded.</span>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </>
            ) : (
              <div className="loading-overlay">
                <div className="spinner-lg" />
                <p className="loading-text">Processing answers…</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  )
}

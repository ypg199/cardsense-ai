import { useState, useEffect, useCallback } from 'react'
import { useParams, useLocation, useNavigate } from 'react-router-dom'
import QuestionCard from '../components/QuestionCard.jsx'
import { Logo, LoadFailed, SampleBadge } from '../components/Brand.jsx'
import { AlertIcon, CheckIcon } from '../components/Icons.jsx'
import { money, monthLabel } from '../format.js'
import { submitAnswer, getSessionStatus } from '../api.js'
import FullScreenLoader, { RESULT_STEPS } from '../components/FullScreenLoader.jsx'

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
  .util-page { padding: 24px 16px 48px; }
  .util-header { margin-bottom: 24px; }
  .util-layout { grid-template-columns: 1fr; gap: 16px; }
  /* Question first on phones; the card summary follows it */
  .right-panel { order: -1; }
  .left-panel { position: static; padding: 18px 16px; border-radius: var(--radius-lg); }
}
.quiz-error {
  display: flex; gap: 8px; align-items: center; margin-top: 14px; padding: 10px 14px;
  border-radius: var(--radius-md); background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.25);
  color: var(--red-400); font-size: 13px;
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
.auto-check { color: var(--green-400); display: inline-flex; }
.auto-item strong { color: var(--slate-200); font-weight: 500; }

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
  border-bottom: 1px solid rgba(var(--tint), 0.04);
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
  const [activeTab, setActiveTab] = useState(0)
  const [loadError, setLoadError] = useState(null)
  const [answerError, setAnswerError] = useState(null)

  const poll = useCallback(async () => {
    try {
      const s = await getSessionStatus(sessionId)
      setSession(s)
      if (s.ui_action === 'show_results') {
        navigate(`/results/${sessionId}`, { state: { session: s } })
      }
    } catch (e) {
      setLoadError(e)
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
    setAnswerError(null)
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
      setAnswerError(e.message || 'Could not save that answer. Please try again.')
    } finally {
      setAnswerLoading(false)
    }
  }

  if (loading) return <FullScreenLoader title="Loading your quiz" steps={['Fetching your session']} />

  if (!session) return <LoadFailed error={loadError} />

  const { current_question, questions_answered, questions_total, cards, current_card_idx } = session
  const activeCard = cards[current_card_idx] || cards[0]
  const progress = questions_total > 0 ? (questions_answered / questions_total) * 100 : 0
  const months = activeCard?.months || []
  const period = months.length > 1
    ? `${monthLabel(months[0], true)} to ${monthLabel(months[months.length - 1], true)}`
    : monthLabel(months[0], true)

  const lastQuestion = questions_total > 0 && questions_answered + 1 >= questions_total

  return (
    <>
      <style>{css}</style>
      {session.ui_action === 'show_loading' && (
        <FullScreenLoader title="Working out your results" steps={RESULT_STEPS} stepEvery={10} showTime />
      )}
      {answerLoading && session.ui_action !== 'show_loading' && (
        lastQuestion
          ? <FullScreenLoader title="Working out your results" steps={RESULT_STEPS} stepEvery={10} showTime />
          : <FullScreenLoader title="Saving your answer" steps={['Updating your quiz']} delay={500} />
      )}
      <div className="util-page">
        <div className="util-header">
          <div><Logo />{session.sample && <SampleBadge />}</div>
          <div className="util-progress-wrap">
            <span className="mono" style={{ fontSize: 12 }}>{questions_answered}/{questions_total}</span>
            <div className="progress-track" role="progressbar" aria-label="Quiz progress" aria-valuemin={0} aria-valuemax={questions_total} aria-valuenow={questions_answered}>
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
            <div className="card-info-bank">Analysing</div>
            <div className="card-info-name">{activeCard?.card_name}</div>

            <div className="auto-detected">
              <div className="auto-detected-title">Read from your statements</div>
              {period && (
                <div className="auto-item"><span className="auto-check"><CheckIcon size={14} /></span><span><strong>{period}</strong></span></div>
              )}
              {activeCard?.transactions_count > 0 && (
                <div className="auto-item"><span className="auto-check"><CheckIcon size={14} /></span><span><strong>{activeCard.transactions_count}</strong> transaction{activeCard.transactions_count === 1 ? '' : 's'}</span></div>
              )}
              {activeCard?.total_spend > 0 && (
                <div className="auto-item"><span className="auto-check"><CheckIcon size={14} /></span><span><strong>{money(activeCard.total_spend)}</strong> spent</span></div>
              )}
            </div>
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

                {answerError && (
                  <div className="quiz-error" role="alert"><AlertIcon size={16} /> {answerError}</div>
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

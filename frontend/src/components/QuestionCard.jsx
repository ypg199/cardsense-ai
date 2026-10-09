import { useState, useEffect } from 'react'

const styles = `
.qcard {
  background: var(--navy-800);
  border: 1px solid var(--navy-600);
  border-radius: var(--radius-xl);
  padding: 32px 28px;
  animation: slideIn 280ms cubic-bezier(0.34, 1.56, 0.64, 1);
}
.qcard-potential {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 20px;
}
.potential-badge {
  background: rgba(245,158,11,0.12);
  border: 1px solid rgba(245,158,11,0.3);
  border-radius: 20px;
  padding: 4px 12px;
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--amber-400);
  font-weight: 500;
}
.qcard-text {
  font-family: var(--font-display);
  font-size: 22px;
  line-height: 1.35;
  color: var(--white);
  margin-bottom: 10px;
}
.qcard-hint {
  font-size: 13px;
  color: var(--slate-400);
  margin-bottom: 8px;
}
.qcard-spend {
  font-size: 12px;
  color: var(--slate-400);
  font-family: var(--font-mono);
  margin-bottom: 28px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.qcard-spend-dot {
  width: 6px;
  height: 6px;
  background: var(--blue-400);
  border-radius: 50%;
}
.qcard-buttons {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.qbtn {
  padding: 16px;
  border-radius: var(--radius-md);
  font-family: var(--font-sans);
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  border: 1.5px solid transparent;
  transition: all var(--transition);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}
.qbtn:disabled { opacity: 0.5; cursor: not-allowed; }
.qbtn-yes {
  background: rgba(34,197,94,0.1);
  border-color: var(--green-500);
  color: var(--green-400);
}
.qbtn-yes:hover:not(:disabled) {
  background: var(--green-500);
  color: var(--navy-950);
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(34,197,94,0.25);
}
.qbtn-no {
  background: rgba(239,68,68,0.08);
  border-color: var(--red-500);
  color: var(--red-400);
}
.qbtn-no:hover:not(:disabled) {
  background: var(--red-500);
  color: var(--white);
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(239,68,68,0.2);
}
`

export default function QuestionCard({ question, onAnswer, loading }) {
  const [answered, setAnswered] = useState(null)

  useEffect(() => {
      setAnswered(null)
    }, [question])
  function handleAnswer(val) {
    if (loading || answered !== null) return
    setAnswered(val)
    setTimeout(() => onAnswer(question.id, val), 280)
  }

  if (!question) return null

  const fmt = (n) => n >= 1000 ? `₹${(n/1000).toFixed(1)}k` : `₹${Math.round(n)}`

  return (
    <>
      <style>{styles}</style>
      <div className="qcard">
        <div className="qcard-potential">
          {question.potential_cashback > 0 && (
            <span className="potential-badge">
              💰 {fmt(question.potential_cashback)} potential
            </span>
          )}
        </div>
        <p className="qcard-text">{question.text}</p>
        <p className="qcard-hint">{question.hint}</p>
        {question.detected_spend > 0 && (
          <div className="qcard-spend">
            <span className="qcard-spend-dot" />
            Detected spend this period: <strong className="amount">{fmt(question.detected_spend)}</strong>
          </div>
        )}
        <div className="qcard-buttons">
          <button
            className="qbtn qbtn-yes"
            disabled={loading || answered !== null}
            onClick={() => handleAnswer(true)}
            style={answered === true ? { background: 'var(--green-500)', color: 'var(--navy-950)' } : {}}
          >
            ✓ Yes
          </button>
          <button
            className="qbtn qbtn-no"
            disabled={loading || answered !== null}
            onClick={() => handleAnswer(false)}
            style={answered === false ? { background: 'var(--red-500)', color: 'var(--white)' } : {}}
          >
            ✕ No
          </button>
        </div>
      </div>
    </>
  )
}

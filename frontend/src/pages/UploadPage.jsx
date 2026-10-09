import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import CardSelector from '../components/CardSelector.jsx'
import PdfDropZone from '../components/PdfDropZone.jsx'
import PasswordModal from '../components/PasswordModal.jsx'
import Tabs from '../components/Tabs.jsx'
import FullScreenLoader, { PARSE_STEPS } from '../components/FullScreenLoader.jsx'
import { startSample, startSession, submitPassword } from '../api.js'
import SampleBanner from '../components/SampleBanner.jsx'
import { Logo } from '../components/Brand.jsx'
import { AlertIcon, ArrowRightIcon } from '../components/Icons.jsx'

export const uploadCss = `
.upload-page {
  min-height: 100vh;
  padding: 0 24px 60px;
  max-width: 900px;
  margin: 0 auto;
}
.page-header {
  padding: 48px 0 40px;
  text-align: center;
  animation: fadeUp 400ms ease both;
}
.logo-mark { margin-bottom: 24px; }
.submit-hint { text-align: center; font-size: 12px; color: var(--slate-400); margin-top: 10px; }
.error-banner svg { flex-shrink: 0; }
@media (max-width: 560px) {
  .upload-page { padding: 0 16px 48px; }
  .page-header { padding: 32px 0 28px; }
  .section { padding: 20px 16px; border-radius: var(--radius-lg); }
  .upload-card { padding: 14px; }
  .upload-card-title { flex-wrap: wrap; }
  .submit-btn { padding: 16px 24px; }
}
.upload-card-title .bank-label { white-space: nowrap; }
.page-title {
  font-family: var(--font-display);
  font-size: clamp(32px, 6vw, 54px);
  line-height: 1.1;
  letter-spacing: -0.02em;
  margin-bottom: 16px;
}
.page-title em { font-style: italic; color: var(--amber-400); }
.page-subtitle {
  font-size: 16px;
  color: var(--slate-400);
  max-width: 500px;
  margin: 0 auto;
  line-height: 1.6;
}
.section {
  background: var(--navy-900);
  border: 1px solid var(--navy-700);
  border-radius: var(--radius-xl);
  padding: 28px 28px;
  margin-bottom: 16px;
  animation: fadeUp 400ms ease both;
}
.section-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
}
.section-step {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: rgba(245,158,11,0.15);
  border: 1px solid rgba(245,158,11,0.4);
  color: var(--amber-400);
  font-size: 12px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.section-title { font-size: 16px; font-weight: 600; color: var(--white); }
.section-subtitle { font-size: 12px; color: var(--slate-400); }

.uploads-grid { display: flex; flex-direction: column; gap: 20px; }
.upload-card {
  border: 1px solid var(--navy-600);
  border-radius: var(--radius-lg);
  padding: 20px;
  background: rgba(var(--tint), 0.02);
}
.upload-card-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--white);
  margin-bottom: 14px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.upload-card-title .bank-label {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--amber-400);
  background: rgba(245,158,11,0.1);
  padding: 2px 8px;
  border-radius: 4px;
}

.submit-btn {
  width: 100%;
  background: linear-gradient(135deg, var(--amber-500), var(--amber-400));
  border: none;
  border-radius: var(--radius-md);
  color: var(--on-accent);
  font-family: var(--font-sans);
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 0.02em;
  padding: 18px 32px;
  cursor: pointer;
  transition: all var(--transition);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  animation: fadeUp 400ms ease both;
  animation-delay: 200ms;
}
.submit-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 12px 40px rgba(245,158,11,0.35);
}
.submit-btn:disabled { opacity: 0.4; cursor: not-allowed; transform: none; box-shadow: none; }

.error-banner {
  background: rgba(239,68,68,0.1);
  border: 1px solid rgba(239,68,68,0.3);
  border-radius: var(--radius-md);
  padding: 14px 18px;
  font-size: 13px;
  color: var(--red-400);
  display: flex;
  align-items: center;
  gap: 10px;
  animation: fadeUp 200ms ease;
}
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 48px;
  text-align: center;
}
.spinner {
  width: 36px;
  height: 36px;
  border: 3px solid var(--navy-600);
  border-top-color: var(--amber-500);
  border-radius: 50%;
  animation: spin 800ms linear infinite;
}
.loading-msg { color: var(--slate-400); font-size: 14px; }

.mode-switch { margin: 32px auto 0; max-width: 560px; }
`
const css = uploadCss

/** Switch between the full card analysis and the standalone Spend Analyser. */
export function ModeSwitch({ active }) {
  const navigate = useNavigate()
  return (
    <div className="mode-switch">
      <Tabs
        variant="secondary"
        label="What do you want to do?"
        value={active}
        onChange={key => key !== active && navigate(key === 'spend' ? '/spend' : '/')}
        items={[
          { key: 'card', label: 'Card analysis', hint: 'Score, quiz and better cards' },
          { key: 'spend', label: 'Spend Analyser', hint: 'Just charts of your spending' },
        ]}
      />
    </div>
  )
}

export default function UploadPage() {
  const navigate = useNavigate()
  const [selected, setSelected] = useState([])   // card objects
  const [fileMap, setFileMap] = useState({})       // card._id → [{file, month}]
  const [sampleLoading, setSampleLoading] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [passwordState, setPasswordState] = useState(null) // { sessionId, cardIdx, cardName, month, error }
  const [pwLoading, setPwLoading] = useState(false)

  function toggleCard(card) {
    const id = card._id || card.id
    setSelected(prev => {
      const exists = prev.find(c => (c._id || c.id) === id)
      if (exists) {
        setFileMap(m => { const n = { ...m }; delete n[id]; return n })
        return prev.filter(c => (c._id || c.id) !== id)
      }
      return [...prev, card]
    })
  }

  function setFiles(cardId, files) {
    setFileMap(m => ({ ...m, [cardId]: files }))
  }

  async function handleSubmit() {
    setError(null)
    const hasFiles = selected.every(c => (fileMap[(c._id || c.id)] || []).length > 0)
    if (!hasFiles) { setError('Please upload at least one PDF for each selected card.'); return }

    setLoading(true)
    const fd = new FormData()
    const pdfFiles = []
    const months = []
    const cardIds = []

    for (const card of selected) {
      const id = card._id || card.id
      const entries = fileMap[id] || []
      for (const e of entries) {
        fd.append('card_ids', id)
        fd.append('pdf_files', e.file, e.file.name)
        fd.append('month_labels', e.month)
        cardIds.push(id)
        pdfFiles.push(e.file)
        months.push(e.month)
      }
    }

    try {
      const resp = await startSession(fd)
      handleResponse(resp)
    } catch (err) {
      setError(err.message || 'Failed to start analysis. Is the API running?')
      setLoading(false)
    }
  }

  async function handleSample() {
    setError(null)
    setSampleLoading(true)
    try {
      handleResponse(await startSample('full'))
    } catch (err) {
      setError(err.message || 'Could not load the sample statements.')
    } finally {
      setSampleLoading(false)
    }
  }

  function handleResponse(resp) {
    if (resp.ui_action === 'show_password_input') {
      const cardIdx = resp.current_card_idx || 0
      const card = resp.cards[cardIdx]
      setPasswordState({
        sessionId: resp.session_id,
        cardIdx,
        cardName: card?.card_name || 'Unknown Card',
        month: (card?.months || [])[0] || '',
        error: resp.error || null,
      })
      setLoading(false)
      return
    }
    if (resp.ui_action === 'show_question' || resp.ui_action === 'show_loading') {
      navigate(`/quiz/${resp.session_id}`, { state: { session: resp } })
      return
    }
    if (resp.ui_action === 'show_results') {
      navigate(`/results/${resp.session_id}`, { state: { session: resp } })
      return
    }
    if (resp.ui_action === 'show_error') {
      setError(resp.error || 'An error occurred during analysis.')
      setLoading(false)
    }
  }

  async function handlePasswordSubmit(password) {
    if (!passwordState) return
    setPwLoading(true)
    try {
      const resp = await submitPassword(passwordState.sessionId, {
        password,
        card_idx: passwordState.cardIdx,
      })
      if (resp.error && resp.ui_action === 'show_password_input') {
        setPasswordState(ps => ({ ...ps, error: resp.error }))
        setPwLoading(false)
        return
      }
      setPasswordState(null)
      setPwLoading(false)
      handleResponse(resp)
    } catch (err) {
      setPasswordState(ps => ({ ...ps, error: err.message }))
      setPwLoading(false)
    }
  }

  const canSubmit = selected.length > 0 && selected.every(c => (fileMap[(c._id || c.id)] || []).length > 0)

  return (
    <>
      <style>{css}</style>

      {passwordState && (
        <PasswordModal
          cardName={passwordState.cardName}
          monthLabel={passwordState.month}
          error={passwordState.error}
          loading={pwLoading}
          onSubmit={handlePasswordSubmit}
        />
      )}

      <div className="upload-page">
        <div className="page-header">
          <div className="logo-mark"><Logo pill /></div>
          <h1 className="page-title">
            Know exactly how well<br />
            you're using your <em>card</em>
          </h1>
          <p className="page-subtitle">
            Upload your statements. We'll score your benefit utilization and show you what you're missing.
          </p>
          <ModeSwitch active="card" />
          <SampleBanner onTry={handleSample} disabled={loading || sampleLoading} />
        </div>

        {/* Step 1: Card Selection */}
        <div className="section" style={{ animationDelay: '50ms' }}>
          <div className="section-header">
            <span className="section-step">1</span>
            <div>
              <div className="section-title">Select your credit card(s)</div>
              <div className="section-subtitle">Choose one or more cards to analyse</div>
            </div>
          </div>
          <CardSelector selected={selected} onToggle={toggleCard} />
        </div>

        {/* Step 2: PDF upload per card */}
        {selected.length > 0 && (
          <div className="section" style={{ animationDelay: '100ms' }}>
            <div className="section-header">
              <span className="section-step">2</span>
              <div>
                <div className="section-title">Upload PDF statements</div>
                <div className="section-subtitle">Upload one or more months per card</div>
              </div>
            </div>
            <div className="uploads-grid">
              {selected.map(card => {
                const id = card._id || card.id
                return (
                  <div key={id} className="upload-card">
                    <div className="upload-card-title">
                      <span className="bank-label">{card.bank}</span>
                      {card.name}
                    </div>
                    <PdfDropZone
                      cardName={card.name}
                      files={fileMap[id] || []}
                      onFilesChange={f => setFiles(id, f)}
                    />
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* Errors */}
        {error && (
          <div className="error-banner" role="alert" style={{ marginBottom: 16 }}>
            <AlertIcon size={16} /> {error}
          </div>
        )}

        {sampleLoading && (
          <FullScreenLoader title="Loading the sample statements" steps={['Reading four months of sample spending', 'Preparing your quiz']} stepEvery={3} />
        )}
        {(loading || pwLoading) && (
          <FullScreenLoader title="Analysing your statements" steps={PARSE_STEPS} stepEvery={8} showTime />
        )}
        <button className="submit-btn" disabled={!canSubmit || loading} onClick={handleSubmit}>
          Analyse my card{selected.length > 1 ? 's' : ''} <ArrowRightIcon size={18} />
        </button>
        {!canSubmit && !loading && (
          <p className="submit-hint">
            {selected.length === 0 ? 'Pick your card above to get started.' : 'Add at least one PDF statement for each card.'}
          </p>
        )}
      </div>
    </>
  )
}

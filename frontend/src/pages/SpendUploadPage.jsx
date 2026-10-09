import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import PdfDropZone from '../components/PdfDropZone.jsx'
import PasswordModal from '../components/PasswordModal.jsx'
import FullScreenLoader, { PARSE_STEPS } from '../components/FullScreenLoader.jsx'
import { startSample, startSession, submitPassword } from '../api.js'
import SampleBanner from '../components/SampleBanner.jsx'
import { ModeSwitch, uploadCss } from './UploadPage.jsx'
import { Logo } from '../components/Brand.jsx'
import { AlertIcon, ArrowRightIcon } from '../components/Icons.jsx'

const css = `
.spend-points { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; margin-bottom: 20px; }
.spend-point {
  font-size: 13px; color: var(--slate-300); background: rgba(var(--tint), 0.02);
  border: 1px solid var(--navy-700); border-radius: var(--radius-md); padding: 12px 14px;
}
.spend-point strong { display: block; color: var(--white); font-weight: 600; margin-bottom: 2px; }
`

/**
 * Standalone Spend Analyser: upload statements and go straight to the charts,
 * with no card selection, quiz or recommendations.
 */
export default function SpendUploadPage() {
  const navigate = useNavigate()
  const [files, setFiles] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [passwordState, setPasswordState] = useState(null)
  const [pwLoading, setPwLoading] = useState(false)

  async function handleSubmit() {
    setError(null)
    setLoading(true)
    const fd = new FormData()
    fd.append('mode', 'spend')
    for (const e of files) {
      fd.append('card_ids', 'my-statements')
      fd.append('pdf_files', e.file, e.file.name)
      fd.append('month_labels', e.month)
    }
    try {
      handleResponse(await startSession(fd))
    } catch (err) {
      setError(err.message || 'Could not read your statements. Is the API running?')
      setLoading(false)
    }
  }

  async function handleSample() {
    setError(null)
    setLoading(true)
    try {
      handleResponse(await startSample('spend'))
    } catch (err) {
      setError(err.message || 'Could not load the sample statements.')
      setLoading(false)
    }
  }

  function handleResponse(resp) {
    if (resp.ui_action === 'show_password_input') {
      const card = resp.cards[resp.current_card_idx || 0]
      setPasswordState({
        sessionId: resp.session_id,
        cardIdx: resp.current_card_idx || 0,
        cardName: 'Your statement',
        month: (card?.months || [])[0] || '',
        error: resp.error || null,
      })
      setLoading(false)
      return
    }
    if (resp.ui_action === 'show_analyser') {
      navigate(`/analyser/${resp.session_id}`)
      return
    }
    setError(resp.error || 'Something went wrong while reading your statements.')
    setLoading(false)
  }

  async function handlePasswordSubmit(password) {
    if (!passwordState) return
    setPwLoading(true)
    try {
      const resp = await submitPassword(passwordState.sessionId, { password, card_idx: passwordState.cardIdx })
      if (resp.error && resp.ui_action === 'show_password_input') {
        setPasswordState(ps => ({ ...ps, error: resp.error }))
        return
      }
      setPasswordState(null)
      handleResponse(resp)
    } catch (err) {
      setPasswordState(ps => ({ ...ps, error: err.message }))
    } finally {
      setPwLoading(false)
    }
  }

  return (
    <>
      <style>{uploadCss + css}</style>

      {passwordState && (
        <PasswordModal
          cardName={passwordState.cardName}
          monthLabel={passwordState.month}
          error={passwordState.error}
          loading={pwLoading}
          onSubmit={handlePasswordSubmit}
        />
      )}
      {(loading || pwLoading) && (
        <FullScreenLoader title="Reading your statements" steps={PARSE_STEPS} stepEvery={8} showTime />
      )}

      <div className="upload-page">
        <div className="page-header">
          <div className="logo-mark"><Logo pill /></div>
          <h1 className="page-title">
            See where your<br />
            money <em>goes</em>
          </h1>
          <p className="page-subtitle">
            Drop in statements from any card. You'll get monthly trends, month-by-month comparisons and your top merchants.
          </p>
          <ModeSwitch active="spend" />
          <SampleBanner onTry={handleSample} disabled={loading} label="See sample spending" />
        </div>

        <div className="section" style={{ animationDelay: '50ms' }}>
          <div className="section-header">
            <span className="section-step">1</span>
            <div>
              <div className="section-title">Upload PDF statements</div>
              <div className="section-subtitle">Several months give the best picture. Password-protected PDFs work too.</div>
            </div>
          </div>
          <div className="spend-points">
            <div className="spend-point"><strong>Monthly trend</strong>Spend per month, split by category</div>
            <div className="spend-point"><strong>Compare months</strong>Any two months side by side</div>
            <div className="spend-point"><strong>Top merchants</strong>Where most of the money went</div>
          </div>
          <PdfDropZone cardName="Your statements" files={files} onFilesChange={setFiles} />
        </div>

        {error && <div className="error-banner" role="alert" style={{ marginBottom: 16 }}><AlertIcon size={16} /> {error}</div>}

        <button className="submit-btn" disabled={files.length === 0 || loading} onClick={handleSubmit}>
          Show my spending <ArrowRightIcon size={18} />
        </button>
        {files.length === 0 && !loading && <p className="submit-hint">Add at least one PDF statement to continue.</p>}
      </div>
    </>
  )
}

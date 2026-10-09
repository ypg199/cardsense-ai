import { useState, useEffect, useRef } from 'react'
import { AlertIcon, EyeIcon, EyeOffIcon, LockIcon } from './Icons.jsx'

const styles = `
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: var(--overlay);
  backdrop-filter: blur(6px);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  animation: fadeIn 200ms ease;
}
.modal {
  background: var(--navy-800);
  border: 1px solid var(--navy-600);
  border-radius: var(--radius-xl);
  padding: 36px;
  width: 100%;
  max-width: 420px;
  animation: fadeUp 250ms ease;
  box-shadow: 0 24px 80px rgba(0,0,0,0.6), 0 0 0 1px rgba(245,158,11,0.1);
}
.modal-icon {
  width: 52px; height: 52px; border-radius: 14px; margin: 0 auto 16px;
  display: flex; align-items: center; justify-content: center;
  background: rgba(245,158,11,0.08); border: 1px solid rgba(245,158,11,0.2); color: var(--amber-400);
  text-align: center;
  animation: pulse-ring 1.5s ease-out infinite;
}
.modal-title {
  font-family: var(--font-display);
  font-size: 22px;
  text-align: center;
  margin-bottom: 6px;
}
.modal-subtitle {
  font-size: 13px;
  color: var(--slate-400);
  text-align: center;
  margin-bottom: 24px;
}
.modal-card-label {
  display: inline-block;
  background: rgba(245,158,11,0.12);
  border: 1px solid rgba(245,158,11,0.3);
  color: var(--amber-400);
  border-radius: 6px;
  padding: 2px 10px;
  font-size: 12px;
  font-weight: 500;
  margin: 0 auto 24px;
  display: block;
  text-align: center;
}
.pw-field {
  position: relative;
  margin-bottom: 12px;
}
.pw-input {
  width: 100%;
  background: var(--navy-900);
  border: 1px solid var(--navy-600);
  border-radius: var(--radius-md);
  color: var(--white);
  font-size: 15px;
  padding: 14px 44px 14px 16px;
  font-family: var(--font-mono);
  letter-spacing: 0.05em;
  transition: border-color var(--transition);
}
.pw-input:focus { outline: none; border-color: var(--amber-500); }
.pw-input.error { border-color: var(--red-500); }
.pw-toggle {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  color: var(--slate-400);
  cursor: pointer;
  font-size: 16px;
  padding: 4px;
  transition: color var(--transition);
}
.pw-toggle:hover { color: var(--white); }
.pw-toggle:focus-visible { outline: 2px solid var(--amber-400); border-radius: 4px; }
.error-msg { display: flex; align-items: center; gap: 6px; }
.error-msg {
  font-size: 12px;
  color: var(--red-400);
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.modal-submit {
  width: 100%;
  background: var(--amber-500);
  border: none;
  border-radius: var(--radius-md);
  color: var(--on-accent);
  font-family: var(--font-sans);
  font-size: 15px;
  font-weight: 600;
  padding: 14px;
  cursor: pointer;
  transition: background var(--transition), transform var(--transition);
}
.modal-submit:hover:not(:disabled) { background: var(--amber-400); transform: translateY(-1px); }
.modal-submit:disabled { opacity: 0.6; cursor: not-allowed; transform: none; }
`

export default function PasswordModal({ cardName, monthLabel, error, onSubmit, loading }) {
  const [password, setPassword] = useState('')
  const [show, setShow] = useState(false)
  const inputRef = useRef()

  useEffect(() => { inputRef.current?.focus() }, [])

  function handleSubmit(e) {
    e?.preventDefault()
    if (!password.trim() || loading) return
    onSubmit(password)
    setPassword('')
  }

  return (
    <>
      <style>{styles}</style>
      <div className="modal-backdrop">
        <div className="modal" role="dialog" aria-modal="true" aria-labelledby="pw-title">
          <span className="modal-icon"><LockIcon size={24} /></span>
          <h2 className="modal-title" id="pw-title">This statement is locked</h2>
          <p className="modal-subtitle">Enter the password to unlock your statement</p>
          <span className="modal-card-label">{cardName}{monthLabel ? ` · ${monthLabel}` : ''}</span>

          <form onSubmit={handleSubmit}>
            <div className="pw-field">
              <input
                ref={inputRef}
                type={show ? 'text' : 'password'}
                className={`pw-input${error ? ' error' : ''}`}
                placeholder="Enter PDF password"
                aria-label="PDF password"
                aria-invalid={!!error}
                value={password}
                onChange={e => setPassword(e.target.value)}
              />
              <button type="button" className="pw-toggle" aria-label={show ? 'Hide password' : 'Show password'} onClick={() => setShow(s => !s)}>
                {show ? <EyeOffIcon size={18} /> : <EyeIcon size={18} />}
              </button>
            </div>

            {error && (
              <div className="error-msg" role="alert"><AlertIcon size={14} /> {error}</div>
            )}

            <button className="modal-submit" type="submit" disabled={!password.trim() || loading}>
              {loading ? 'Verifying…' : 'Unlock statement'}
            </button>
          </form>
        </div>
      </div>
    </>
  )
}

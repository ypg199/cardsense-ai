import { useState, useRef } from 'react'

const styles = `
.dropzone {
  border: 2px dashed var(--navy-600);
  border-radius: var(--radius-md);
  padding: 28px 20px;
  text-align: center;
  cursor: pointer;
  transition: border-color var(--transition), background var(--transition);
  background: rgba(255,255,255,0.02);
  position: relative;
}
.dropzone:hover, .dropzone.drag-over {
  border-color: var(--amber-500);
  background: rgba(245,158,11,0.04);
}
.dropzone-icon {
  font-size: 28px;
  margin-bottom: 8px;
  display: block;
}
.dropzone-label {
  font-size: 13px;
  color: var(--slate-400);
}
.dropzone-label strong { color: var(--amber-400); }
.file-list { margin-top: 16px; display: flex; flex-direction: column; gap: 8px; }
.file-item {
  display: flex;
  align-items: center;
  gap: 10px;
  background: rgba(255,255,255,0.04);
  border: 1px solid var(--navy-600);
  border-radius: var(--radius-sm);
  padding: 10px 14px;
  animation: fadeUp 200ms ease both;
}
.file-icon { font-size: 18px; flex-shrink: 0; }
.file-info { flex: 1; min-width: 0; }
.file-name {
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--white);
}
.file-meta {
  font-size: 11px;
  color: var(--slate-400);
  margin-top: 2px;
  display: flex;
  gap: 8px;
  align-items: center;
}
.file-encrypted {
  background: rgba(245,158,11,0.15);
  color: var(--amber-400);
  border-radius: 4px;
  padding: 1px 6px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.05em;
}
.month-input {
  background: var(--navy-800);
  border: 1px solid var(--navy-600);
  border-radius: var(--radius-sm);
  color: var(--white);
  font-family: var(--font-mono);
  font-size: 12px;
  padding: 4px 8px;
  width: 90px;
}
.month-input:focus { outline: none; border-color: var(--amber-500); }
.remove-btn {
  background: none;
  border: none;
  color: var(--slate-400);
  cursor: pointer;
  font-size: 16px;
  padding: 2px;
  line-height: 1;
  flex-shrink: 0;
  transition: color var(--transition);
}
.remove-btn:hover { color: var(--red-400); }
`

function guessMonth(filename) {
  const match = filename.match(/(\d{4})[-_]?(\d{2})/)
  if (match) return `${match[1]}-${match[2]}`
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

function isLikelyEncrypted(name) {
  return /passw|encrypt|protect|secured/i.test(name)
}

function fmt(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1048576).toFixed(1)} MB`
}

export default function PdfDropZone({ cardName, files, onFilesChange }) {
  const [dragOver, setDragOver] = useState(false)
  const inputRef = useRef()

  function addFiles(fileList) {
    const newEntries = Array.from(fileList)
      .filter(f => f.type === 'application/pdf' || f.name.endsWith('.pdf'))
      .map(f => ({ file: f, month: guessMonth(f.name) }))
    onFilesChange([...files, ...newEntries])
  }

  function updateMonth(idx, val) {
    const updated = files.map((e, i) => i === idx ? { ...e, month: val } : e)
    onFilesChange(updated)
  }

  function remove(idx) {
    onFilesChange(files.filter((_, i) => i !== idx))
  }

  return (
    <>
      <style>{styles}</style>
      <div
        className={`dropzone${dragOver ? ' drag-over' : ''}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={e => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={e => { e.preventDefault(); setDragOver(false); addFiles(e.dataTransfer.files) }}
      >
        <span className="dropzone-icon">📄</span>
        <p className="dropzone-label">
          Drop PDFs for <strong>{cardName}</strong> here<br />
          or click to browse — multiple months supported
        </p>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".pdf,application/pdf"
          style={{ display: 'none' }}
          onChange={e => addFiles(e.target.files)}
        />
      </div>

      {files.length > 0 && (
        <div className="file-list">
          {files.map((entry, idx) => (
            <div key={idx} className="file-item">
              <span className="file-icon">📋</span>
              <div className="file-info">
                <div className="file-name">{entry.file.name}</div>
                <div className="file-meta">
                  <span>{fmt(entry.file.size)}</span>
                  {isLikelyEncrypted(entry.file.name) && (
                    <span className="file-encrypted">🔒 ENCRYPTED</span>
                  )}
                </div>
              </div>
              <input
                className="month-input"
                value={entry.month}
                onChange={e => updateMonth(idx, e.target.value)}
                placeholder="YYYY-MM"
                onClick={e => e.stopPropagation()}
              />
              <button className="remove-btn" onClick={e => { e.stopPropagation(); remove(idx) }}>✕</button>
            </div>
          ))}
        </div>
      )}
    </>
  )
}

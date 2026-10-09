import { useState, useRef } from 'react'
import { FileIcon, LockIcon, UploadIcon, XIcon } from './Icons.jsx'

const styles = `
.dropzone {
  border: 2px dashed var(--navy-600);
  border-radius: var(--radius-md);
  padding: 28px 20px;
  text-align: center;
  cursor: pointer;
  transition: border-color var(--transition), background var(--transition);
  background: rgba(var(--tint), 0.02);
  position: relative;
}
.dropzone:focus-visible { outline: 2px solid var(--amber-400); outline-offset: 2px; }
.dropzone:hover, .dropzone.drag-over {
  border-color: var(--amber-500);
  background: rgba(245,158,11,0.04);
}
.dropzone-icon {
  width: 44px; height: 44px; margin: 0 auto 10px; border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
  background: rgba(245,158,11,0.08); color: var(--amber-400);
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
  background: rgba(var(--tint), 0.04);
  border: 1px solid var(--navy-600);
  border-radius: var(--radius-sm);
  padding: 10px 14px;
  animation: fadeUp 200ms ease both;
}
.file-icon { flex-shrink: 0; color: var(--slate-400); display: flex; }
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
.month-input:focus { outline: none; border-color: var(--amber-500); box-shadow: 0 0 0 3px rgba(245,158,11,0.2); }
.remove-btn {
  background: none;
  border: none;
  color: var(--slate-400);
  cursor: pointer;
  padding: 6px;
  border-radius: var(--radius-sm);
  display: flex;
  flex-shrink: 0;
  transition: color var(--transition), background var(--transition);
}
.remove-btn:hover { color: var(--red-400); background: rgba(239,68,68,0.08); }
.remove-btn:focus-visible { outline: 2px solid var(--amber-400); }
.file-encrypted { display: inline-flex; align-items: center; gap: 4px; }
/* Phones: give the file name the full row and drop the month below it */
@media (max-width: 560px) {
  .file-item { flex-wrap: wrap; row-gap: 8px; padding: 10px 10px 10px 12px; }
  .file-info { flex: 1 1 calc(100% - 80px); }
  .remove-btn { order: 2; }
  .month-input { order: 3; margin-left: 28px; width: 110px; }
}
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
        role="button"
        tabIndex={0}
        aria-label={`Add PDF statements for ${cardName}`}
        onClick={() => inputRef.current?.click()}
        onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); inputRef.current?.click() } }}
        onDragOver={e => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={e => { e.preventDefault(); setDragOver(false); addFiles(e.dataTransfer.files) }}
      >
        <span className="dropzone-icon"><UploadIcon size={22} /></span>
        <p className="dropzone-label">
          Drop PDFs for <strong>{cardName}</strong> here<br />
          or click to browse. One file per month, as many months as you like.
        </p>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".pdf,application/pdf"
          style={{ display: 'none' }}
          onChange={e => { addFiles(e.target.files); e.target.value = '' }}
        />
      </div>

      {files.length > 0 && (
        <div className="file-list">
          {files.map((entry, idx) => (
            <div key={idx} className="file-item">
              <span className="file-icon"><FileIcon size={18} /></span>
              <div className="file-info">
                <div className="file-name" title={entry.file.name}>{entry.file.name}</div>
                <div className="file-meta">
                  <span>{fmt(entry.file.size)}</span>
                  {isLikelyEncrypted(entry.file.name) && (
                    <span className="file-encrypted"><LockIcon size={11} /> ENCRYPTED</span>
                  )}
                </div>
              </div>
              <input
                className="month-input"
                value={entry.month}
                onChange={e => updateMonth(idx, e.target.value)}
                placeholder="YYYY-MM"
                aria-label={`Statement month for ${entry.file.name}`}
                onClick={e => e.stopPropagation()}
              />
              <button type="button" className="remove-btn" aria-label={`Remove ${entry.file.name}`} onClick={e => { e.stopPropagation(); remove(idx) }}><XIcon size={16} /></button>
            </div>
          ))}
        </div>
      )}
    </>
  )
}

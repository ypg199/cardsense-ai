import { useState, useEffect } from 'react'
import { getCards, searchCards } from '../api.js'
import { CheckIcon, SearchIcon } from './Icons.jsx'
import { money } from '../format.js'

const styles = `
.card-selector { display: flex; flex-direction: column; gap: 16px; }
.search-bar {
  position: relative;
}
.search-input {
  width: 100%;
  background: var(--navy-800);
  border: 1px solid var(--navy-600);
  border-radius: var(--radius-md);
  color: var(--white);
  font-family: var(--font-sans);
  font-size: 14px;
  padding: 12px 16px 12px 42px;
  transition: border-color var(--transition);
}
.search-input::placeholder { color: var(--slate-400); }
.search-input:focus { outline: none; border-color: var(--amber-500); }
.search-icon {
  position: absolute;
  left: 14px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--slate-400);
  display: flex;
  pointer-events: none;
}
.search-input:focus-visible { box-shadow: 0 0 0 3px rgba(245,158,11,0.2); }
.selector-top { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; }
.selector-top .search-bar { flex: 1 1 260px; }
.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 10px;
  max-height: 420px;
  overflow-y: auto;
  padding: 2px 4px 24px 2px;
  /* Fade the last row so it's clear the list scrolls */
  -webkit-mask-image: linear-gradient(to bottom, #000 calc(100% - 40px), transparent);
  mask-image: linear-gradient(to bottom, #000 calc(100% - 40px), transparent);
}
@media (max-width: 560px) {
  .card-grid { grid-template-columns: 1fr; max-height: 380px; }
}
.card-item {
  background: var(--navy-800);
  border: 1.5px solid var(--navy-600);
  border-radius: var(--radius-md);
  padding: 14px 16px;
  cursor: pointer;
  transition: border-color var(--transition), background var(--transition), transform var(--transition);
  position: relative;
  user-select: none;
  width: 100%;
  text-align: left;
  font-family: var(--font-sans);
  color: inherit;
}
.card-item:focus-visible { outline: 2px solid var(--amber-400); outline-offset: 2px; }
.card-item:hover {
  border-color: var(--navy-500);
  background: var(--navy-700);
  transform: translateY(-1px);
}
.card-item.selected {
  border-color: var(--amber-500);
  background: rgba(245,158,11,0.06);
  box-shadow: var(--shadow-glow-amber);
}
.card-check {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  border: 1.5px solid var(--navy-500);
  background: var(--navy-900);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  transition: all var(--transition);
}
.card-item.selected .card-check {
  background: var(--amber-500);
  border-color: var(--amber-500);
  color: var(--on-accent);
}
.card-bank {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--slate-400);
  margin-bottom: 4px;
}
.card-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--white);
  margin-bottom: 8px;
  padding-right: 24px;
  line-height: 1.3;
}
.card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-bottom: 10px;
}
.card-tag {
  background: rgba(var(--tint), 0.06);
  border-radius: 4px;
  font-size: 10px;
  padding: 2px 7px;
  color: var(--slate-300);
}
.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.card-fee {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--slate-400);
}
.network-badge {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.05em;
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--navy-700);
  color: var(--slate-300);
}
.no-results {
  text-align: center;
  padding: 40px 20px;
  color: var(--slate-400);
  font-size: 14px;
}
.loading-cards {
  display: flex;
  justify-content: center;
  padding: 40px;
  color: var(--slate-400);
}
.selected-count {
  font-size: 12px;
  color: var(--amber-400);
  font-weight: 500;
}
`

export default function CardSelector({ selected, onToggle }) {
  const [cards, setCards] = useState([])
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getCards({ limit: 50 })
      .then(d => setCards(d.cards || []))
      .catch(() => setCards([]))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!query.trim()) {
      getCards({ limit: 50 }).then(d => setCards(d.cards || [])).catch(() => {})
      return
    }
    const t = setTimeout(() => {
      searchCards(query).then(d => setCards(d.cards || [])).catch(() => {})
    }, 300)
    return () => clearTimeout(t)
  }, [query])

  const selectedIds = new Set(selected.map(c => c._id || c.id))

  return (
    <>
      <style>{styles}</style>
      <div className="card-selector">
        <div className="selector-top">
          <div className="search-bar">
            <span className="search-icon"><SearchIcon size={17} /></span>
            <input
              className="search-input"
              type="search"
              aria-label="Search cards"
              placeholder="Search cards by name or bank…"
              value={query}
              onChange={e => setQuery(e.target.value)}
            />
          </div>
          {selected.length > 0 && (
            <span className="selected-count" aria-live="polite">
              {selected.length} selected
            </span>
          )}
        </div>

        {loading ? (
          <div className="loading-cards">Loading cards…</div>
        ) : cards.length === 0 ? (
          <div className="no-results">
            {query.trim() ? `No cards match "${query.trim()}". Try a bank name like HDFC or Axis.` : 'No cards available right now.'}
          </div>
        ) : (
          <div className="card-grid">
            {cards.map(card => {
              const id = card._id || card.id
              const isSel = selectedIds.has(id)
              return (
                <button
                  type="button"
                  key={id}
                  className={`card-item${isSel ? ' selected' : ''}`}
                  aria-pressed={isSel}
                  onClick={() => onToggle(card)}
                >
                  <div className="card-check" aria-hidden="true">{isSel && <CheckIcon size={12} strokeWidth={3} />}</div>
                  <div className="card-bank">{card.bank}</div>
                  <div className="card-name">{card.name}</div>
                  <div className="card-tags">
                    {(card.best_for_tags || []).slice(0, 2).map(t => (
                      <span key={t} className="card-tag">{t}</span>
                    ))}
                  </div>
                  <div className="card-footer">
                    <span className="card-fee">
                      {card.annual_fee === 0 ? 'Free forever' : `${money(card.annual_fee)}/yr`}
                    </span>
                    <span className="network-badge">{card.network}</span>
                  </div>
                </button>
              )
            })}
          </div>
        )}
      </div>
    </>
  )
}

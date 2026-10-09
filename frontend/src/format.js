/**
 * format.js — number, month and category formatting shared by every page.
 */
const inr = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })
export const money = v => `₹${inr.format(Math.round(v))}`

export function compactMoney(v) {
  const a = Math.abs(v)
  if (a >= 1e7) return `₹${(v / 1e7).toFixed(1).replace(/\.0$/, '')}Cr`
  if (a >= 1e5) return `₹${(v / 1e5).toFixed(1).replace(/\.0$/, '')}L`
  if (a >= 1e3) return `₹${(v / 1e3).toFixed(a >= 1e4 ? 0 : 1).replace(/\.0$/, '')}k`
  return `₹${Math.round(v)}`
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
export function monthLabel(m, long = false) {
  const match = /^(\d{4})-(\d{2})$/.exec(m || '')
  if (!match) return m
  const name = MONTHS[Number(match[2]) - 1]
  return long ? `${name} ${match[1]}` : `${name} ’${match[1].slice(2)}`
}

export const catLabel = cat =>
  cat === 'other_group' ? 'Other' : cat.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())

/** "2024-01-12" -> "12 Jan 2024"; anything else is returned unchanged. */
export function dayLabel(d) {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(d || '')
  if (!match) return d
  return `${Number(match[3])} ${MONTHS[Number(match[2]) - 1]} ${match[1]}`
}

/**
 * trivia.js — short credit card facts and puns that rotate in the slow
 * loaders, so a minute of parsing reads as something to enjoy, not a stall.
 * Facts are kept general and India-focused; rates and rules vary by bank.
 */
export const TRIVIA = [
  { kind: 'fact', text: "India's first credit card was issued by Central Bank of India in 1980." },
  { kind: 'fact', text: 'RuPay, India’s own card network, was launched by NPCI in 2012.' },
  { kind: 'fact', text: 'Since 2022 you can link a RuPay credit card to UPI and pay by scanning any QR code.' },
  { kind: 'fact', text: 'CIBIL scores run from 300 to 900. Most banks look for 750 or more.' },
  { kind: 'fact', text: 'Paying only the minimum due means interest on the whole bill, often over 40% a year.' },
  { kind: 'fact', text: 'Pay the full bill on time and you can get up to about 50 days of interest-free credit.' },
  { kind: 'fact', text: 'Keeping your card balance under 30% of the limit is a common rule of thumb for a healthier score.' },
  { kind: 'fact', text: 'Cash withdrawals on a credit card are charged interest from day one, plus a fee.' },
  { kind: 'fact', text: 'A reward point is often worth just ₹0.25, so 1,000 points may be only ₹250.' },
  { kind: 'fact', text: 'The last digit of a card number is a check digit, worked out with the Luhn formula.' },
  { kind: 'fact', text: 'A card starting with 4 is Visa, 5 is usually Mastercard and 3 is Amex or Diners.' },
  { kind: 'fact', text: 'Since October 2022, RBI rules stop online shops from storing your full card number. They keep a token instead.' },
  { kind: 'fact', text: 'Ask your bank to close a card and RBI rules give it 7 working days, or it pays you ₹500 a day.' },
  { kind: 'fact', text: 'Fuel surcharge waivers often apply only to bills in a set range, such as ₹400 to ₹4,000.' },
  { kind: 'fact', text: 'The story goes that Diners Club, one of the first charge cards, began in 1950 after a forgotten wallet at dinner.' },
  { kind: 'pun', text: 'Giving your transactions the credit they deserve…' },
  { kind: 'pun', text: 'Reading the fine print, so you don’t have to.' },
  { kind: 'pun', text: 'Counting every rupee. Twice, because we take your money seriously.' },
  { kind: 'pun', text: 'No interest is charged on this wait. We checked.' },
  { kind: 'pun', text: 'Swiping through your statement, one line at a time.' },
  { kind: 'pun', text: 'Your cashback is out there. We’re tracking it down.' },
  { kind: 'pun', text: 'Good things come to those who wait. So does cashback, usually at month end.' },
]

/** A shuffled copy, so each wait shows a different run of items. */
export function shuffled(items = TRIVIA) {
  const out = [...items]
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[out[i], out[j]] = [out[j], out[i]]
  }
  return out
}

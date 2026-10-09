# Extraction benchmark

Measures how accurately CardSense turns a statement PDF into transactions. It runs the same steps as the API: decrypt, extract text, then parse with Gemini. The output is scored against hand-built ground truth.

Latest results: [RESULTS.md](RESULTS.md)

## The statements

`statements/` holds seven **synthetic** statements, each a PDF plus a JSON file with the true transactions. None of them contain real data. They copy the layout conventions of four Indian issuers, so the benchmark checks that parsing isn't tied to one bank's format:

| File | Layout | What it tests |
|---|---|---|
| `axis_flipkart` | `DD/MM/YYYY`, separate Dr/Cr column | baseline |
| `axis_airtel_enc` | same, AES-256 password-protected (password `SAMP0101`) | decryption, EMI and refund rows |
| `hdfc_millennia` | `DD/MM/YYYY HH:MM:SS`, reward points column, `Cr` suffix | timestamps, extra numeric column |
| `hdfc_regalia_2pg` | as above, 60 rows over 2 pages | page breaks, repeated headers |
| `hdfc_infinia_long` | 180 rows over 5 pages after a long terms section | statements longer than one Gemini request |
| `icici_coral` | serial numbers, foreign-currency column, `CR` suffix | USD row, extra columns |
| `sbi_cashback` | `05 Feb 26` dates, `D`/`C` suffix, descriptions wrapped onto two lines | date format, multi-line rows |

Merchant descriptions mix clean names with the payment-gateway prefixes and terminal ids that real statements carry (`PYU*SWIGGY`, `RAZ*ZEPTO`, `POS 4521 ...`).

## How it's scored

Only spending (debit) rows are scored. The parser deliberately skips bill payments and cashback credits, because the utilization score is built on spend.

A parsed row matches a true row when the amounts agree to the paisa. When several rows share an amount, the one with the same date wins. From the matches:

- **Recall**: the share of true transactions that were found.
- **Precision**: the share of parsed rows that are real.
- **Date and category accuracy**: measured over the matched rows.
- **Total spend error**: the relative difference in total spend, which is what the utilization score is built on.

## Running it

```bash
python -m eval.make_statements          # regenerate the PDFs and ground truth (deterministic)
GEMINI_API_KEY=... python -m eval.run_eval --runs 3
```

The benchmark calls Gemini for real, so it isn't part of CI. The scoring logic is unit-tested in `tests/test_long_statements.py`.

## What it has caught

- **Long statements lost their last transactions.** Text was cut off at 10,000 characters, so the 5-page statement came back with 169 of 180 transactions and spend 7.7% too low. The parser now sends long statements in parts, split between lines, and all 180 come back.
- **One bad Gemini reply could drop a whole statement.** In one run, Gemini returned malformed JSON for one statement and unrelated text for another, so both statements parsed to nothing. Parsing now uses Gemini's JSON mode and retries once when the reply isn't a transaction list.

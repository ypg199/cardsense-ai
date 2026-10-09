"""
db/schemas.py
─────────────────────────────────────────────────────────────────────────────
MongoDB document shapes for CardSense AI.
This file is DOCUMENTATION ONLY — no runtime code.
All shapes reflect the canonical spec (Section 4).
─────────────────────────────────────────────────────────────────────────────


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COLLECTION: credit_cards
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
One document per credit card.
Upserted by the crawler.  _id is a URL-safe slug, e.g. "axis-airtel-credit-card".

{
    "_id":                  str,        # URL-safe slug, e.g. "axis-airtel-credit-card"
    "name":                 str,        # Full card name, e.g. "Axis Airtel Credit Card"
    "bank":                 str,        # Issuing bank, e.g. "Axis Bank"
    "network":              str,        # "Visa" | "Mastercard" | "RuPay" | "Amex"
    "card_type":            str,        # "cashback" | "travel" | "fuel" | "lifestyle" | "co-branded"
    "annual_fee":           int,        # INR; 0 if lifetime free
    "fee_waiver_spend":     int | None, # Annual spend (INR) required to waive fee; null = no waiver
    "joining_fee":          int,        # INR
    "min_annual_income":    int | None, # INR; null if not disclosed
    "min_credit_score":     int | None, # e.g. 700; null if not disclosed

    # ── Benefits ─────────────────────────────────────────────────────────
    # Array — one object per benefit/cashback category offered by the card.
    "benefits": [
        {
            "category":              str,        # snake_case internal key, e.g. "airtel_recharge"
            "label":                 str,        # Human-readable, e.g. "Airtel Recharge"
            "rate":                  float,      # Decimal fraction: 25% → 0.25
            "max_cashback_per_month": float | None,  # INR cap per month; null = uncapped
            "reward_type":           str,        # "cashback" | "points" | "miles"
            "point_value_inr":       float | None,   # Value of 1 point in INR; null for cashback
            "conditions":            str | None, # Free-text conditions string or null
            "merchant_keywords":     [str],      # Lowercase words to match against txn merchant name
        }
    ],

    # ── Utilization questions ────────────────────────────────────────────
    # Card-specific YES/NO questions shown on the UtilizationPage quiz.
    "utilization_questions": [
        {
            "id":                   str,    # Unique question ID, e.g. "q_airtel_sim"
            "text":                 str,    # Question shown to user
            "hint":                 str,    # Benefit hint, e.g. "Earns 25% cashback on Airtel recharges"
            "maps_to_category":     str,    # Matching benefit category key
            "auto_detect_keywords": [str],  # If any txn merchant contains these, auto-answer = True
        }
    ],

    "best_for_tags":    [str],      # Short descriptive tags, e.g. ["airtel users", "zomato"]
    "not_good_for":     [str],      # e.g. ["amazon", "travel", "fuel"]
    "source_url":       str,        # URL from which card data was crawled
    "last_crawled":     str,        # ISO-8601 datetime string, e.g. "2024-01-15T10:30:00Z"

    # ── Atlas Vector Search ───────────────────────────────────────────────
    # 768-dimensional float array from text-embedding-004.
    # Atlas Vector Search index name: "credit_cards_embedding_index"
    # numDimensions: 768, similarity: cosine
    "embedding":        [float],    # 768 floats
    "embedding_text":   str,        # Source text used to generate the embedding
}


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COLLECTION: sessions
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
One document per analysis session.
TTL index on "created_at" → auto-deleted after 48 hours.
LangGraph MongoDB checkpointer also writes its own checkpoint documents
into the "checkpoints" collection (managed by langgraph-checkpoint-mongodb).

{
    "_id":                  str,    # UUID v4 session ID
    "status":               str,    # See STATUS VALUES below

    # ── Per-card data array ───────────────────────────────────────────────
    # Supports multiple cards per session.
    "cards": [
        {
            "card_id":          str,        # Matches credit_cards._id slug
            "months":           [str],      # ISO month labels, e.g. ["2024-01", "2024-02"]
            "pdf_encrypted":    bool,       # Whether the uploaded PDF was password-protected
            "pdf_text":         str,        # Extracted plain text from all PDFs for this card
            "transactions":     [           # Parsed transaction list (output of parse_node)
                {
                    "date":             str,    # "YYYY-MM-DD"
                    "merchant":         str,    # Cleaned merchant name
                    "amount":           float,  # Positive float (debit amount in INR)
                    "transaction_type": str,    # "debit" | "credit" | "refund"
                    "category":         str,    # One of the 16 standard categories (see below)
                    "month":            str,    # Source month label, e.g. "2024-01"
                }
            ],
            "qa_answers":       dict,       # { question_id: bool } — user YES/NO answers
            "cashback_result":  {           # Output of cashback_calc_node
                "earned_breakdown":     dict,   # { category: float } — INR earned per category
                "missed_breakdown":     dict,   # { category: float } — INR missed per category
                "utilization_score":    int,    # 0–100 integer
                "monthly_breakdown":    [       # Per-month detail (multi-month uploads)
                    {
                        "month":        str,
                        "earned":       float,
                        "missed":       float,
                        "score":        int,
                    }
                ],
                "trend":                str,    # "improving" | "declining" | "flat" | "single_month"
            },
            "utilization_score":    int,    # 0–100 (mirror of cashback_result.utilization_score)
            "status":               str,    # Per-card pipeline status
        }
    ],

    # ── Comparison result ─────────────────────────────────────────────────
    # Output of compare_node; null until status == "done".
    "comparison_result": {
        "verdict":          str,        # "Good fit" | "Could do better" | "Switch recommended"
        "verdict_reason":   str,        # One sentence with specific numbers
        "card_score":       int,        # 0–100 overall card efficiency score
        "recommendations":  [           # Up to 3 alternative cards
            {
                "card_id":                          str,
                "card_name":                        str,
                "bank":                             str,
                "estimated_monthly_cashback":       float,  # INR
                "estimated_annual_cashback":        float,  # INR
                "improvement_over_current_monthly": float,  # INR
                "why_better":                       str,    # 2 sentences
                "best_categories":                  [str],
                "caveat":                           str | None,
            }
        ],
        "routing_advice":   [str],  # Multi-card routing tips, e.g. "Use Axis Airtel for Zomato"
        "tips":             [str],  # 3–5 actionable spend tips
    },

    "current_card_idx": int,        # Index into "cards" array currently being processed
    "created_at":       str,        # ISO-8601; TTL index on this field (48-hour expiry)
    "error":            str | None, # Error message if status == "error", else null
}

# ── Session STATUS VALUES ─────────────────────────────────────────────────
# "uploading"     — user is selecting cards / uploading PDFs
# "pdf_locked"    — at least one PDF is password-protected; waiting for user input
# "parsing"       — LangGraph is extracting transactions from PDFs
# "questioning"   — quiz is in progress; graph interrupted at wait_answer node
# "calculating"   — cashback_calc_node is running
# "comparing"     — compare_node is running (Gemini Pro)
# "done"          — full pipeline complete; results available
# "error"         — unrecoverable error; see "error" field


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COLLECTION: crawl_jobs
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
One document per background crawl task triggered via POST /crawl or Celery beat.

{
    "_id":          str,        # UUID v4 job ID
    "status":       str,        # "pending" | "running" | "done" | "failed"
    "sources":      [str],      # Source keys requested, e.g. ["cardinsider", "bankbazaar"]
    "direct_urls":  [str],      # Any explicit URLs passed in the request body
    "cards_upserted": int,      # Count of successfully upserted cards
    "cards_failed": int,        # Count of failed card extractions
    "errors":       [str],      # Per-URL error messages
    "created_at":   str,        # ISO-8601
    "finished_at":  str | None, # ISO-8601; null while running
}


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STANDARD TRANSACTION CATEGORIES (16 values)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Used in transactions[].category and benefits[].category:

    airtel_recharge
    utility_bills
    food_delivery
    grocery
    shopping_online
    shopping_offline
    travel_flights
    travel_hotels
    fuel
    entertainment
    emi
    insurance
    healthcare
    education
    rent
    others


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INDEX SUMMARY (see db/setup_indexes.py for creation code)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Collection       Index name                          Type            Notes
──────────────── ─────────────────────────────────── ─────────────── ───────────────────────────────────
credit_cards     credit_cards_text_search            TEXT            name + bank + best_for_tags
credit_cards     credit_cards_card_type              ASCENDING       filter by card_type
credit_cards     credit_cards_bank                   ASCENDING       filter by bank
credit_cards     credit_cards_last_crawled           ASCENDING       crawl freshness queries
credit_cards     credit_cards_embedding_index        VECTOR SEARCH   ⚠ Create manually in Atlas UI
                                                                     field: embedding, dims: 768, cosine
sessions         sessions_ttl_48h                    TTL             expireAfterSeconds: 172800
sessions         sessions_status                     ASCENDING       admin status queries
crawl_jobs       crawl_jobs_created_at               ASCENDING       job listing
crawl_jobs       crawl_jobs_status                   ASCENDING       filter by status
"""

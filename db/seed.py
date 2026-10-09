"""
db/seed.py
─────────────────────────────────────────────────────────────────────────────
Seed 5 test cards into MongoDB credit_cards collection.
Run BEFORE starting the API server so the card selector has data.

Usage:
    python -m db.seed

Section 15 of the spec provides these exact 5 cards.
─────────────────────────────────────────────────────────────────────────────
"""

import asyncio
import logging
from datetime import UTC, datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")
logger = logging.getLogger(__name__)

SEED_CARDS = [
    {
        "_id": "axis-airtel",
        "name": "Axis Airtel Credit Card",
        "bank": "Axis Bank",
        "network": "Visa",
        "card_type": "cashback",
        "annual_fee": 500,
        "fee_waiver_spend": 200000,
        "joining_fee": 500,
        "min_annual_income": 300000,
        "min_credit_score": 700,
        "benefits": [
            {
                "category": "airtel_recharge",
                "label": "Airtel Recharge",
                "rate": 0.25,
                "max_cashback_per_month": None,
                "reward_type": "cashback",
                "point_value_inr": None,
                "conditions": "Must pay via Airtel Thanks app",
                "merchant_keywords": ["airtel"],
            },
            {
                "category": "utility_bills",
                "label": "Utility Bills",
                "rate": 0.10,
                "max_cashback_per_month": None,
                "reward_type": "cashback",
                "point_value_inr": None,
                "conditions": None,
                "merchant_keywords": ["bescom", "msedcl"],
            },
            {
                "category": "food_delivery",
                "label": "Zomato",
                "rate": 0.10,
                "max_cashback_per_month": None,
                "reward_type": "cashback",
                "point_value_inr": None,
                "conditions": None,
                "merchant_keywords": ["zomato"],
            },
            {
                "category": "grocery",
                "label": "BigBasket",
                "rate": 0.10,
                "max_cashback_per_month": None,
                "reward_type": "cashback",
                "point_value_inr": None,
                "conditions": None,
                "merchant_keywords": ["bigbasket"],
            },
            {
                "category": "others",
                "label": "Others",
                "rate": 0.01,
                "max_cashback_per_month": None,
                "reward_type": "cashback",
                "point_value_inr": None,
                "conditions": None,
                "merchant_keywords": ["*"],
            },
        ],
        "utilization_questions": [
            {
                "id": "q_airtel_sim",
                "text": "Do you recharge your Airtel mobile SIM using this card?",
                "hint": "Earns 25% cashback on Airtel recharges",
                "maps_to_category": "airtel_recharge",
                "auto_detect_keywords": ["airtel prepaid", "airtel postpaid", "airtel recharge", "airtel"],
            },
            {
                "id": "q_utility",
                "text": "Do you pay your electricity and utility bills with this card?",
                "hint": "Earns 10% cashback on utility bill payments",
                "maps_to_category": "utility_bills",
                "auto_detect_keywords": ["bescom", "msedcl", "mahanagar gas", "tata power"],
            },
            {
                "id": "q_zomato",
                "text": "Do you order food on Zomato using this card?",
                "hint": "Earns 10% cashback on Zomato orders",
                "maps_to_category": "food_delivery",
                "auto_detect_keywords": ["zomato"],
            },
            {
                "id": "q_bigbasket",
                "text": "Do you shop for groceries on BigBasket with this card?",
                "hint": "Earns 10% cashback on BigBasket purchases",
                "maps_to_category": "grocery",
                "auto_detect_keywords": ["bigbasket"],
            },
        ],
        "best_for_tags": ["airtel users", "zomato", "bigbasket"],
        "not_good_for": ["amazon", "travel", "fuel"],
        "source_url": "https://www.axisbank.com/retail/cards/credit-card/axis-bank-airtel-credit-card",
        "last_crawled": datetime.now(UTC).isoformat(),
        "embedding": [],
        "embedding_text": "Axis Airtel Credit Card by Axis Bank. Benefits: Airtel Recharge 25%, Utility Bills 10%, Zomato 10%, BigBasket 10%",
    },
    {
        "_id": "axis-flipkart",
        "name": "Axis Flipkart Credit Card",
        "bank": "Axis Bank",
        "network": "Visa",
        "card_type": "cashback",
        "annual_fee": 500,
        "fee_waiver_spend": 200000,
        "joining_fee": 500,
        "min_annual_income": 300000,
        "min_credit_score": 700,
        "benefits": [
            {
                "category": "shopping_online",
                "label": "Flipkart & Myntra",
                "rate": 0.05,
                "max_cashback_per_month": None,
                "reward_type": "cashback",
                "point_value_inr": None,
                "conditions": None,
                "merchant_keywords": ["flipkart", "myntra"],
            },
            {
                "category": "travel_flights",
                "label": "Travel",
                "rate": 0.04,
                "max_cashback_per_month": None,
                "reward_type": "cashback",
                "point_value_inr": None,
                "conditions": None,
                "merchant_keywords": ["makemytrip", "goibibo"],
            },
            {
                "category": "others",
                "label": "Others",
                "rate": 0.015,
                "max_cashback_per_month": None,
                "reward_type": "cashback",
                "point_value_inr": None,
                "conditions": None,
                "merchant_keywords": ["*"],
            },
        ],
        "utilization_questions": [
            {
                "id": "q_flipkart_shop",
                "text": "Do you shop on Flipkart or Myntra using this card?",
                "hint": "Earns 5% cashback on Flipkart and Myntra purchases",
                "maps_to_category": "shopping_online",
                "auto_detect_keywords": ["flipkart", "myntra"],
            },
            {
                "id": "q_travel_mmt",
                "text": "Do you book flights or hotels via MakeMyTrip or Goibibo with this card?",
                "hint": "Earns 4% cashback on travel bookings",
                "maps_to_category": "travel_flights",
                "auto_detect_keywords": ["makemytrip", "goibibo", "indigo", "spicejet"],
            },
        ],
        "best_for_tags": ["flipkart shoppers", "fashion", "travel"],
        "not_good_for": ["amazon", "airtel", "grocery"],
        "source_url": "https://www.axisbank.com/retail/cards/credit-card/flipkart-axis-bank-credit-card",
        "last_crawled": datetime.now(UTC).isoformat(),
        "embedding": [],
        "embedding_text": "Axis Flipkart Credit Card by Axis Bank. Benefits: Flipkart Myntra 5%, Travel 4%, Others 1.5%",
    },
    {
        "_id": "hdfc-millennia",
        "name": "HDFC Millennia Credit Card",
        "bank": "HDFC Bank",
        "network": "Mastercard",
        "card_type": "cashback",
        "annual_fee": 1000,
        "fee_waiver_spend": 100000,
        "joining_fee": 1000,
        "min_annual_income": 350000,
        "min_credit_score": 720,
        "benefits": [
            {
                "category": "shopping_online",
                "label": "Amazon & Flipkart",
                "rate": 0.05,
                "max_cashback_per_month": None,
                "reward_type": "cashback",
                "point_value_inr": None,
                "conditions": None,
                "merchant_keywords": ["amazon", "flipkart"],
            },
            {
                "category": "food_delivery",
                "label": "Dining & Food Delivery",
                "rate": 0.05,
                "max_cashback_per_month": None,
                "reward_type": "cashback",
                "point_value_inr": None,
                "conditions": None,
                "merchant_keywords": ["zomato", "swiggy"],
            },
            {
                "category": "grocery",
                "label": "Grocery",
                "rate": 0.05,
                "max_cashback_per_month": None,
                "reward_type": "cashback",
                "point_value_inr": None,
                "conditions": None,
                "merchant_keywords": ["bigbasket", "blinkit"],
            },
            {
                "category": "others",
                "label": "Others",
                "rate": 0.01,
                "max_cashback_per_month": None,
                "reward_type": "cashback",
                "point_value_inr": None,
                "conditions": None,
                "merchant_keywords": ["*"],
            },
        ],
        "utilization_questions": [
            {
                "id": "q_millennia_amazon",
                "text": "Do you shop on Amazon using this card?",
                "hint": "Earns 5% cashback on Amazon purchases",
                "maps_to_category": "shopping_online",
                "auto_detect_keywords": ["amazon"],
            },
            {
                "id": "q_millennia_swiggy",
                "text": "Do you order food via Swiggy or Zomato with this card?",
                "hint": "Earns 5% cashback on food delivery orders",
                "maps_to_category": "food_delivery",
                "auto_detect_keywords": ["swiggy", "zomato"],
            },
            {
                "id": "q_millennia_grocery",
                "text": "Do you buy groceries on BigBasket or Blinkit with this card?",
                "hint": "Earns 5% cashback on grocery purchases",
                "maps_to_category": "grocery",
                "auto_detect_keywords": ["bigbasket", "blinkit", "zepto"],
            },
        ],
        "best_for_tags": ["amazon", "dining", "grocery", "online shopping"],
        "not_good_for": ["airtel recharge", "fuel"],
        "source_url": "https://www.hdfcbank.com/personal/pay/cards/credit-cards/millennia-credit-card",
        "last_crawled": datetime.now(UTC).isoformat(),
        "embedding": [],
        "embedding_text": "HDFC Millennia Credit Card by HDFC Bank. Benefits: Amazon Flipkart 5%, Dining Food 5%, Grocery 5%, Others 1%",
    },
    {
        "_id": "sbi-cashback",
        "name": "SBI Cashback Credit Card",
        "bank": "SBI Card",
        "network": "Visa",
        "card_type": "cashback",
        "annual_fee": 999,
        "fee_waiver_spend": 200000,
        "joining_fee": 999,
        "min_annual_income": 300000,
        "min_credit_score": 700,
        "benefits": [
            {
                "category": "shopping_online",
                "label": "All Online Shopping",
                "rate": 0.05,
                "max_cashback_per_month": 5000,
                "reward_type": "cashback",
                "point_value_inr": None,
                "conditions": "Applies to all online transactions",
                "merchant_keywords": ["*online*"],
            },
            {
                "category": "others",
                "label": "Offline Spends",
                "rate": 0.01,
                "max_cashback_per_month": None,
                "reward_type": "cashback",
                "point_value_inr": None,
                "conditions": None,
                "merchant_keywords": ["*"],
            },
        ],
        "utilization_questions": [
            {
                "id": "q_sbi_online",
                "text": "Do you primarily use this card for online shopping?",
                "hint": "Earns 5% cashback on ALL online spends — platform agnostic",
                "maps_to_category": "shopping_online",
                "auto_detect_keywords": ["amazon", "flipkart", "myntra", "nykaa", "meesho"],
            },
        ],
        "best_for_tags": ["online shopping", "platform agnostic", "5% flat cashback"],
        "not_good_for": ["offline purchases", "fuel", "rent"],
        "source_url": "https://www.sbicard.com/en/personal/credit-cards/cashback/sbi-card-cashback.page",
        "last_crawled": datetime.now(UTC).isoformat(),
        "embedding": [],
        "embedding_text": "SBI Cashback Credit Card by SBI Card. Benefits: All Online Shopping 5%, Offline Spends 1%",
    },
    {
        "_id": "icici-amazon",
        "name": "Amazon Pay ICICI Card",
        "bank": "ICICI Bank",
        "network": "Visa",
        "card_type": "co-branded",
        "annual_fee": 0,
        "fee_waiver_spend": None,
        "joining_fee": 0,
        "min_annual_income": 250000,
        "min_credit_score": 680,
        "benefits": [
            {
                "category": "shopping_online",
                "label": "Amazon Prime Members",
                "rate": 0.05,
                "max_cashback_per_month": None,
                "reward_type": "cashback",
                "point_value_inr": None,
                "conditions": "Must be Amazon Prime member",
                "merchant_keywords": ["amazon"],
            },
            {
                "category": "others",
                "label": "Others",
                "rate": 0.01,
                "max_cashback_per_month": None,
                "reward_type": "cashback",
                "point_value_inr": None,
                "conditions": None,
                "merchant_keywords": ["*"],
            },
        ],
        "utilization_questions": [
            {
                "id": "q_amazon_prime",
                "text": "Are you an Amazon Prime member using this card for Amazon purchases?",
                "hint": "Prime members earn 5% cashback on all Amazon spends",
                "maps_to_category": "shopping_online",
                "auto_detect_keywords": ["amazon"],
            },
        ],
        "best_for_tags": ["amazon prime", "lifetime free", "zero annual fee"],
        "not_good_for": ["non-amazon spending", "travel", "fuel"],
        "source_url": "https://www.icicibank.com/personal-banking/cards/credit-card/amazon-pay-credit-card",
        "last_crawled": datetime.now(UTC).isoformat(),
        "embedding": [],
        "embedding_text": "Amazon Pay ICICI Card by ICICI Bank. Benefits: Amazon Prime 5%, Others 1%. Lifetime free card.",
    },
]


async def seed_cards() -> None:
    from db.connection import close_db, get_db, ping_db

    logger.info("=== CardSense AI — Seed Data ===")
    ok = await ping_db()
    if not ok:
        logger.error("Cannot connect to MongoDB. Aborting seed.")
        return

    db = get_db()
    col = db["credit_cards"]
    upserted = 0
    skipped = 0

    for card in SEED_CARDS:
        result = await col.update_one(
            {"_id": card["_id"]},
            {"$set": card},
            upsert=True,
        )
        if result.upserted_id or result.modified_count:
            logger.info("  Upserted: %s (%s)", card["name"], card["_id"])
            upserted += 1
        else:
            logger.info("  No change: %s (already up-to-date)", card["name"])
            skipped += 1

    logger.info("Seed complete — %d upserted, %d unchanged", upserted, skipped)
    await close_db()


if __name__ == "__main__":
    asyncio.run(seed_cards())

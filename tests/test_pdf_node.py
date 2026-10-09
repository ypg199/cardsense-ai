"""
tests/test_pdf_node.py
Standalone test for agents/pdf_node.py — no pytest required.
Creates real in-memory PDFs using PyMuPDF so tests are self-contained.
"""

import io
import os
import sys

import fitz

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.pdf_node import _decrypt_pdf, _extract_with_pdfplumber, _extract_with_pymupdf, pdf_check_node
from agents.state import AnalysisState, CardState

# ─────────────────────────────────────────────────────────────────────────────
# Helpers to create real PDFs in-memory
# ─────────────────────────────────────────────────────────────────────────────

SAMPLE_STATEMENT = """
AXIS BANK CREDIT CARD STATEMENT
Account Number: XXXX-XXXX-XXXX-1234
Statement Period: 01-Jan-2024 to 31-Jan-2024

Date        Description                  Amount (INR)
01-Jan-2024 ZOMATO ORDER #ZOM123         450.00
05-Jan-2024 AIRTEL PREPAID RECHARGE      299.00
10-Jan-2024 AMAZON PURCHASE              1200.00
15-Jan-2024 BIGBASKET GROCERY            850.00
20-Jan-2024 BESCOM ELECTRICITY BILL      1500.00
25-Jan-2024 SWIGGY FOOD ORDER            320.00
28-Jan-2024 FLIPKART PURCHASE            3000.00

Total Spend: 7619.00
"""


def _make_pdf_bytes(text: str = SAMPLE_STATEMENT) -> bytes:
    """Create a real PDF with text content using PyMuPDF."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), text, fontsize=10)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def _make_encrypted_pdf(text: str = SAMPLE_STATEMENT, password: str = "test123") -> bytes:
    """Create a real password-protected PDF."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), text, fontsize=10)
    buf = io.BytesIO()
    doc.save(buf, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw=password, owner_pw=password)
    doc.close()
    return buf.getvalue()


def _make_state(
    pdf_bytes_list: list[bytes],
    pdf_passwords: list[str | None] | None = None,
    months: list[str] | None = None,
    card_id: str = "axis-airtel",
    card_name: str = "Axis Airtel Credit Card",
    card_idx: int = 0,
) -> AnalysisState:
    """Build a minimal AnalysisState for testing."""
    card: CardState = {
        "card_id": card_id,
        "card_name": card_name,
        "months": months or ["2024-01"] * len(pdf_bytes_list),
        "pdf_bytes_list": pdf_bytes_list,
        "pdf_passwords": pdf_passwords or [None] * len(pdf_bytes_list),
        "pdf_encrypted": False,
        "pdf_text": "",
        "transactions": [],
        "total_spend": 0.0,
        "pending_questions": [],
        "answered_questions": [],
        "qa_answers": {},
        "cashback_result": None,
        "utilization_score": 0,
        "status": "uploading",
    }
    return {
        "session_id": "test-session-001",
        "status": "uploading",
        "cards": [card],
        "current_card_idx": card_idx,
        "locked_card_idx": None,
        "locked_pdf_idx": None,
        "current_question": None,
        "comparison_result": None,
        "ui_action": "show_upload",
        "total_questions_count": 0,
        "answered_questions_count": 0,
        "error": None,
        "created_at": "2024-01-01T00:00:00Z",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

PASS = 0
FAIL = 0


def ok(msg: str):
    global PASS
    PASS += 1
    print(f"  ✅ {msg}")


def fail(msg: str):
    global FAIL
    FAIL += 1
    print(f"  ❌ {msg}")


def test_plain_pdf_extraction():
    print("\n[1] Plain PDF — single month")
    pdf_bytes = _make_pdf_bytes()
    state = _make_state([pdf_bytes], months=["2024-01"])
    result = pdf_check_node(state)

    assert result["status"] == "parsing", f"Expected 'parsing', got {result['status']}"
    ok("status == 'parsing'")

    assert result["ui_action"] == "show_loading"
    ok("ui_action == 'show_loading'")

    card = result["cards"][0]
    assert card["status"] == "parsing"
    ok("card.status == 'parsing'")

    assert len(card["pdf_text"]) > 50
    ok(f"pdf_text extracted ({len(card['pdf_text'])} chars)")

    assert "ZOMATO" in card["pdf_text"] or "zomato" in card["pdf_text"].lower()
    ok("merchant names present in extracted text")

    assert card["pdf_bytes_list"] == []
    ok("pdf_bytes_list cleared after extraction")

    assert card["pdf_encrypted"] == False
    ok("pdf_encrypted == False for plain PDF")

    assert result["locked_card_idx"] is None
    assert result["locked_pdf_idx"] is None
    ok("locked_card_idx / locked_pdf_idx cleared")


def test_multi_month_pdf():
    print("\n[2] Multi-month PDF — two statements")
    pdf1 = _make_pdf_bytes("STATEMENT JAN\nZOMATO 450\nAIRTEL 299")
    pdf2 = _make_pdf_bytes("STATEMENT FEB\nAMAZON 1200\nBIGBASKET 850")
    state = _make_state([pdf1, pdf2], months=["2024-01", "2024-02"])
    result = pdf_check_node(state)

    assert result["status"] == "parsing"
    ok("status == 'parsing' for multi-month")

    card = result["cards"][0]
    text = card["pdf_text"]

    assert "2024-01" in text
    ok("month label 2024-01 in concatenated text")

    assert "2024-02" in text
    ok("month label 2024-02 in concatenated text")

    assert "ZOMATO" in text or "AMAZON" in text
    ok("transactions from both months present")

    assert len(card["pdf_bytes_list"]) == 0
    ok("pdf_bytes_list cleared (both months)")


def test_encrypted_pdf_no_password():
    print("\n[3] Encrypted PDF — no password supplied")
    enc_bytes = _make_encrypted_pdf(password="secret99")
    state = _make_state([enc_bytes], pdf_passwords=[None], months=["2024-01"])
    result = pdf_check_node(state)

    assert result["status"] == "pdf_locked", f"Expected 'pdf_locked', got {result['status']}"
    ok("status == 'pdf_locked'")

    assert result["ui_action"] == "show_password_input"
    ok("ui_action == 'show_password_input'")

    assert result["locked_card_idx"] == 0
    ok("locked_card_idx == 0")

    assert result["locked_pdf_idx"] == 0
    ok("locked_pdf_idx == 0")

    assert result["error"] is None
    ok("error is None (first attempt, no error message)")


def test_encrypted_pdf_wrong_password():
    print("\n[4] Encrypted PDF — wrong password")
    enc_bytes = _make_encrypted_pdf(password="correct_pw")
    state = _make_state([enc_bytes], pdf_passwords=["wrong_pw"], months=["2024-01"])
    result = pdf_check_node(state)

    assert result["status"] == "pdf_locked"
    ok("status == 'pdf_locked' after wrong password")

    assert result["ui_action"] == "show_password_input"
    ok("ui_action == 'show_password_input'")

    assert result["error"] is not None
    assert "wrong" in result["error"].lower() or "password" in result["error"].lower()
    ok(f"error message set: '{result['error']}'")


def test_encrypted_pdf_correct_password():
    print("\n[5] Encrypted PDF — correct password supplied")
    password = "mypassword"
    enc_bytes = _make_encrypted_pdf(text=SAMPLE_STATEMENT, password=password)
    state = _make_state([enc_bytes], pdf_passwords=[password], months=["2024-01"])
    result = pdf_check_node(state)

    assert result["status"] == "parsing", f"Expected 'parsing', got {result['status']}"
    ok("status == 'parsing' after correct password")

    card = result["cards"][0]
    assert card["pdf_encrypted"] == True
    ok("pdf_encrypted == True (was encrypted)")

    assert len(card["pdf_text"]) > 20
    ok(f"text extracted after decryption ({len(card['pdf_text'])} chars)")

    assert card["pdf_bytes_list"] == []
    ok("pdf_bytes_list cleared")


def test_no_pdf_bytes():
    print("\n[6] No PDF bytes — error state")
    state = _make_state([])
    result = pdf_check_node(state)

    assert result["status"] == "error"
    ok("status == 'error' when no PDF bytes")

    assert result["ui_action"] == "show_error"
    ok("ui_action == 'show_error'")

    assert result["error"] is not None
    ok(f"error message set: '{result['error']}'")


def test_multi_card_correct_idx():
    print("\n[7] Multi-card state — only active card processed")
    pdf1 = _make_pdf_bytes("CARD ONE TRANSACTIONS\nZOMATO 450")
    pdf2 = _make_pdf_bytes("CARD TWO TRANSACTIONS\nAMAZON 1200")

    card1: CardState = {
        "card_id": "axis-airtel",
        "card_name": "Axis Airtel",
        "months": ["2024-01"],
        "pdf_bytes_list": [pdf1],
        "pdf_passwords": [None],
        "pdf_encrypted": False,
        "pdf_text": "",
        "transactions": [],
        "total_spend": 0.0,
        "pending_questions": [],
        "answered_questions": [],
        "qa_answers": {},
        "cashback_result": None,
        "utilization_score": 0,
        "status": "uploading",
    }
    card2: CardState = {
        "card_id": "hdfc-millennia",
        "card_name": "HDFC Millennia",
        "months": ["2024-01"],
        "pdf_bytes_list": [pdf2],
        "pdf_passwords": [None],
        "pdf_encrypted": False,
        "pdf_text": "",
        "transactions": [],
        "total_spend": 0.0,
        "pending_questions": [],
        "answered_questions": [],
        "qa_answers": {},
        "cashback_result": None,
        "utilization_score": 0,
        "status": "uploading",
    }

    state: AnalysisState = {
        "session_id": "test-multi-card",
        "status": "uploading",
        "cards": [card1, card2],
        "current_card_idx": 1,  # Process second card
        "locked_card_idx": None,
        "locked_pdf_idx": None,
        "current_question": None,
        "comparison_result": None,
        "ui_action": "show_upload",
        "total_questions_count": 0,
        "answered_questions_count": 0,
        "error": None,
        "created_at": "2024-01-01T00:00:00Z",
    }

    result = pdf_check_node(state)

    assert result["status"] == "parsing"
    ok("status == 'parsing'")

    # Card at idx=1 should be processed
    processed_card = result["cards"][1]
    assert "AMAZON" in processed_card["pdf_text"] or len(processed_card["pdf_text"]) > 0
    ok("correct card (idx=1) was processed")

    # Card at idx=0 should be untouched
    untouched_card = result["cards"][0]
    assert untouched_card["pdf_text"] == ""
    ok("card at idx=0 untouched")


def test_helpers_directly():
    print("\n[8] Direct helper tests")

    # _extract_with_pymupdf
    pdf_bytes = _make_pdf_bytes("PYMUPDF TEST\nAIRTEL 299")
    text = _extract_with_pymupdf(pdf_bytes)
    assert "PYMUPDF TEST" in text or "AIRTEL" in text
    ok("_extract_with_pymupdf returns text")

    # _extract_with_pdfplumber
    text2 = _extract_with_pdfplumber(pdf_bytes)
    assert len(text2) > 0
    ok("_extract_with_pdfplumber returns text")

    # _decrypt_pdf on plain PDF
    plain_bytes, was_enc = _decrypt_pdf(pdf_bytes, None)
    assert was_enc == False
    ok("_decrypt_pdf: plain PDF, was_encrypted=False")

    # _decrypt_pdf on encrypted PDF — no password
    enc_bytes = _make_encrypted_pdf(password="pw123")
    try:
        _decrypt_pdf(enc_bytes, None)
        fail("Should have raised ValueError('pdf_locked')")
    except ValueError as e:
        assert str(e) == "pdf_locked"
        ok("_decrypt_pdf raises ValueError('pdf_locked') when encrypted + no password")

    # _decrypt_pdf on encrypted PDF — wrong password
    try:
        _decrypt_pdf(enc_bytes, "wrongpw")
        fail("Should have raised ValueError('wrong_password')")
    except ValueError as e:
        assert str(e) == "wrong_password"
        ok("_decrypt_pdf raises ValueError('wrong_password')")

    # _decrypt_pdf on encrypted PDF — correct password
    dec_bytes, was_enc = _decrypt_pdf(enc_bytes, "pw123")
    assert was_enc == True
    assert len(dec_bytes) > 0
    ok("_decrypt_pdf: correct password, returns decrypted bytes")


# ─────────────────────────────────────────────────────────────────────────────
# Run all tests
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  pdf_node test suite")
    print("=" * 60)

    test_plain_pdf_extraction()
    test_multi_month_pdf()
    test_encrypted_pdf_no_password()
    test_encrypted_pdf_wrong_password()
    test_encrypted_pdf_correct_password()
    test_no_pdf_bytes()
    test_multi_card_correct_idx()
    test_helpers_directly()

    print()
    print("=" * 60)
    print(f"  Results: {PASS} passed, {FAIL} failed")
    print("=" * 60)

    if FAIL > 0:
        sys.exit(1)

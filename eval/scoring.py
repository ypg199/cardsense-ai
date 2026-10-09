"""
eval/scoring.py
─────────────────────────────────────────────────────────────────────────────
Compare parsed transactions with a statement's ground truth.

A predicted row matches a true row when the amounts agree to the paisa; when
several rows share an amount, the one with the same date wins. Matched pairs
are then checked field by field (date, debit/credit type, category).
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StatementScore:
    name: str
    true_rows: int = 0
    predicted_rows: int = 0
    matched: int = 0
    date_correct: int = 0
    type_correct: int = 0
    debits_matched: int = 0
    category_correct: int = 0
    true_debit_total: float = 0.0
    predicted_debit_total: float = 0.0
    misses: list[dict] = field(default_factory=list)
    extras: list[dict] = field(default_factory=list)
    wrong_category: list[tuple[dict, dict]] = field(default_factory=list)

    @property
    def precision(self) -> float:
        return self.matched / self.predicted_rows if self.predicted_rows else 0.0

    @property
    def recall(self) -> float:
        return self.matched / self.true_rows if self.true_rows else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0

    @property
    def category_accuracy(self) -> float:
        return self.category_correct / self.debits_matched if self.debits_matched else 0.0

    @property
    def spend_error(self) -> float:
        """Relative error of total debit spend (what the cashback score is built on)."""
        if not self.true_debit_total:
            return 0.0
        return abs(self.predicted_debit_total - self.true_debit_total) / self.true_debit_total


def _is_debit(row: dict) -> bool:
    return row.get("transaction_type", "debit") == "debit"


def score_statement(name: str, truth: list[dict], predicted: list[dict]) -> StatementScore:
    s = StatementScore(name=name, true_rows=len(truth), predicted_rows=len(predicted))
    s.true_debit_total = round(sum(t["amount"] for t in truth if _is_debit(t)), 2)
    s.predicted_debit_total = round(sum(float(p.get("amount", 0)) for p in predicted if _is_debit(p)), 2)

    unmatched = list(range(len(predicted)))
    for t in truth:
        candidates = [i for i in unmatched if abs(float(predicted[i].get("amount", 0)) - t["amount"]) < 0.005]
        if not candidates:
            s.misses.append(t)
            continue
        same_day = [i for i in candidates if predicted[i].get("date") == t["date"]]
        i = (same_day or candidates)[0]
        unmatched.remove(i)
        p = predicted[i]

        s.matched += 1
        s.date_correct += p.get("date") == t["date"]
        s.type_correct += _is_debit(p) == _is_debit(t)
        if _is_debit(t):
            s.debits_matched += 1
            if p.get("category") == t["category"]:
                s.category_correct += 1
            else:
                s.wrong_category.append((t, p))

    s.extras = [predicted[i] for i in unmatched]
    return s


def summarise(scores: list[StatementScore]) -> dict[str, float]:
    """Micro-averaged totals across statements."""
    true_rows = sum(s.true_rows for s in scores)
    predicted = sum(s.predicted_rows for s in scores)
    matched = sum(s.matched for s in scores)
    debits = sum(s.debits_matched for s in scores)
    precision = matched / predicted if predicted else 0.0
    recall = matched / true_rows if true_rows else 0.0
    true_spend = sum(s.true_debit_total for s in scores)
    return {
        "statements": len(scores),
        "true_rows": true_rows,
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        "date_accuracy": sum(s.date_correct for s in scores) / matched if matched else 0.0,
        "type_accuracy": sum(s.type_correct for s in scores) / matched if matched else 0.0,
        "category_accuracy": sum(s.category_correct for s in scores) / debits if debits else 0.0,
        "spend_error": (
            abs(sum(s.predicted_debit_total for s in scores) - true_spend) / true_spend if true_spend else 0.0
        ),
    }
